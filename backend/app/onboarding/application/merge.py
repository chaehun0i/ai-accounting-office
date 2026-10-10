"""Preview 행은 저장하지 않고 원본과 최신 초안을 다시 읽어 병합합니다."""

import hashlib
import re
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from app.contracts.access_errors import AuthorizationDenied, ResourceNotFound, StateConflict
from app.identity.users.domain.entities import Principal
from app.intake.application.service import PREVIEW_TTL_SECONDS, IntakeService
from app.intake.domain.canonical_fields import SourceType, TargetContext
from app.intake.domain.digest import digest
from app.intake.domain.entities import Import
from app.intake.domain.errors import IdempotencyConflict
from app.onboarding.application.contracts import OnboardingUnitOfWork
from app.onboarding.application.service import OnboardingService
from app.onboarding.domain.entities import ImportLink, MergeItem, MergePreview, Receipt, Workspace
from app.onboarding.domain.errors import InvalidValue, StaleDraft
from app.onboarding.domain.template import read_template
from app.onboarding.domain.validation import invalidate
from app.onboarding.domain.values import classify


class OnboardingImportService:
    def __init__(self, workspace: OnboardingService, intake: IntakeService) -> None:
        self.workspace, self.intake = workspace, intake

    def upload(
        self, actor: Principal, company: UUID, filename: str, content: bytes, content_type: str
    ) -> ImportLink:
        with self.workspace.factory() as uow:
            current = self.workspace.workspace(uow, actor, company, "onboarding.import")
            if current.status == "COMPLETED":
                raise StateConflict()
        metadata, _, _ = read_template(self.intake.parser(filename, content, content_type))
        value = self.intake.upload(
            actor,
            company,
            source=SourceType.ONBOARDING_TEMPLATE,
            target=TargetContext.ONBOARDING_DRAFT,
            source_system="ONBOARDING_TEMPLATE",
            filename=filename,
            content=content,
            content_type=content_type,
        )
        with self.workspace.factory() as uow:
            current = self.workspace.workspace(uow, actor, company, "onboarding.import")
            return uow.onboarding.link(current, value, metadata)

    def _get(
        self, uow: OnboardingUnitOfWork, actor: Principal, company: UUID, identifier: UUID
    ) -> tuple[Workspace, Import, ImportLink]:
        current = self.workspace.workspace(uow, actor, company, "onboarding.import")
        value = uow.imports.get(company_id=company, resource_id=identifier)
        link = uow.onboarding.import_link(company, identifier)
        if value is None or link is None or link.session_id != current.id:
            raise ResourceNotFound()
        if value.requested_by != actor.user_id:
            raise AuthorizationDenied()
        return current, value, link

    def get(self, actor: Principal, company: UUID, identifier: UUID) -> ImportLink:
        with self.workspace.factory() as uow:
            return self._get(uow, actor, company, identifier)[2]

    def _preview(self, current: Workspace, value: Import, expires_at: datetime) -> MergePreview:
        content = self.intake.storage.read(value.company_id, value.storage_key)
        if hashlib.sha256(content).hexdigest() != value.file_sha256:
            raise StaleDraft()
        _, cells, errors = read_template(
            self.intake.parser(value.original_filename, content, value.content_type)
        )
        existing = {(c.field_code, c.row_key): c for c in current.cells}
        items = [
            MergeItem(
                c,
                existing.get((c.field_code, c.row_key)),
                classify(existing.get((c.field_code, c.row_key)), c),
            )
            for c in cells
        ]
        signature = digest(
            {
                "file": value.file_sha256,
                "session": str(current.id),
                "version": current.version,
                "mapping_version": value.mapping_version,
                "definition": "onboarding-merge-1",
                "source": value.source_type.value,
                "target": value.target_context.value,
                "cells": [(c.field_code, c.row_key, str(c.value)) for c in cells],
            }
        )
        return MergePreview(value.id, current.version, signature, expires_at, items, errors)

    def preview(
        self, actor: Principal, company: UUID, identifier: UUID, expected_version: int
    ) -> MergePreview:
        with self.workspace.factory() as uow:
            current, value, link = self._get(uow, actor, company, identifier)
            self.workspace.writable(current, expected_version)
            if link.status == "APPLIED":
                raise StateConflict()
            expires = uow.now() + timedelta(seconds=PREVIEW_TTL_SECONDS)
        result = self._preview(current, value, expires)
        with self.workspace.factory() as uow:
            latest, imported, _ = self._get(uow, actor, company, identifier)
            self.workspace.writable(latest, expected_version)
            uow.imports.preview(imported, result.digest, expires, [], uow.now())
        return result

    def apply(
        self,
        actor: Principal,
        company: UUID,
        identifier: UUID,
        expected_version: int,
        preview_digest: str,
        choices: dict[str, str],
        key: str,
    ) -> Receipt:
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", key):
            raise InvalidValue()
        fingerprint = digest(
            {
                "import": str(identifier),
                "version": expected_version,
                "digest": preview_digest,
                "choices": choices,
            }
        )
        with self.workspace.factory() as uow:
            current, value, link = self._get(uow, actor, company, identifier)
            replay = uow.onboarding.receipt(company, key)
            if replay:
                if replay.fingerprint != fingerprint:
                    raise IdempotencyConflict()
                return replay
            self.workspace.writable(current, expected_version)
            if link.status == "APPLIED":
                raise IdempotencyConflict()
            if (
                value.preview_expires_at is None
                or value.preview_expires_at <= uow.now()
                or value.preview_digest != preview_digest
            ):
                raise StaleDraft()
        result = self._preview(current, value, value.preview_expires_at)
        if result.digest != preview_digest or result.errors:
            raise StaleDraft()
        with self.workspace.factory() as uow:
            latest, imported, _ = self._get(uow, actor, company, identifier)
            replay = uow.onboarding.receipt(company, key)
            if replay:
                if replay.fingerprint != fingerprint:
                    raise IdempotencyConflict()
                return replay
            self.workspace.writable(latest, expected_version)
            if (
                imported.preview_digest != result.digest
                or imported.preview_expires_at is None
                or imported.preview_expires_at <= uow.now()
            ):
                raise StaleDraft()
            cells = {(c.field_code, c.row_key): c for c in latest.cells}
            counts = {"APPLY": 0, "CHANGED": 0, "UNCHANGED": 0, "CONFLICT": 0}
            conflict_keys = {
                f"{i.incoming.field_code}:{i.incoming.row_key}"
                for i in result.items
                if i.classification == "CONFLICT"
            }
            if set(choices) != conflict_keys or any(
                v not in {"KEEP_CURRENT", "APPLY_IMPORT"} for v in choices.values()
            ):
                raise InvalidValue()
            changed_sections: set[str] = set()
            for item in result.items:
                classification = item.classification
                counts[classification] += 1
                choice = choices.get(f"{item.incoming.field_code}:{item.incoming.row_key}")
                if classification == "APPLY" or choice == "APPLY_IMPORT":
                    cells[(item.incoming.field_code, item.incoming.row_key)] = item.incoming
                    changed_sections.add(item.incoming.field_code.split(".")[0])
                    if choice == "APPLY_IMPORT":
                        counts["CHANGED"] += 1
            saved = uow.onboarding.save(
                latest,
                invalidate(list(cells.values()), changed_sections),
                actor.user_id,
                uow.now(),
                source_import=identifier,
            )
            receipt = Receipt(
                uuid4(),
                saved.id,
                identifier,
                fingerprint,
                counts["APPLY"],
                counts["CHANGED"],
                counts["UNCHANGED"],
                counts["CONFLICT"],
                0,
                uow.now(),
            )
            uow.onboarding.record(saved, receipt, key)
            return receipt
