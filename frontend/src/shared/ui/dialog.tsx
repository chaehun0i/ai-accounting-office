"use client";
import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { useRef, type ReactNode } from "react";

/** 팝업의 포커스 이동·닫기·배경 스크롤 잠금을 한 곳에서 관리합니다. */
export function OfficeDialog({ open, onClose, title, description, children, busy = false, footer, compact = false }: {
  open: boolean; onClose: () => void; title: string; description: string;
  children: ReactNode; busy?: boolean; footer?: ReactNode; compact?: boolean;
}) {
  const returnFocus = useRef<HTMLElement | null>(null);
  return <Dialog.Root open={open} onOpenChange={value => { if (!value && !busy) onClose(); }}>
    <Dialog.Portal><Dialog.Overlay className="dialog-overlay" />
      <Dialog.Content className={`office-dialog${compact ? " dialog-compact" : ""}`} onOpenAutoFocus={() => { returnFocus.current = document.activeElement as HTMLElement | null; }} onCloseAutoFocus={event => { event.preventDefault(); if (returnFocus.current?.isConnected) returnFocus.current.focus(); }} onEscapeKeyDown={event => { if (busy) event.preventDefault(); }} onPointerDownOutside={event => event.preventDefault()}>
        <div className="dialog-heading"><div><span className="eyebrow">회계 업무</span><Dialog.Title>{title}</Dialog.Title><Dialog.Description>{description}</Dialog.Description></div>
          <Dialog.Close asChild><button className="icon-button" aria-label="팝업 닫기" disabled={busy}><X size={20} aria-hidden="true" /></button></Dialog.Close></div>
        <div className="dialog-body" aria-busy={busy}>{children}</div>
        <div className="dialog-footer">{footer}<Dialog.Close asChild><button disabled={busy}>닫기</button></Dialog.Close></div>
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>;
}

export function ConfirmationDialog({ open, onClose, onConfirm, busy, title, description, children, confirmLabel }: {
  open: boolean; onClose: () => void; onConfirm: () => void; busy: boolean;
  title: string; description: string; children: ReactNode; confirmLabel: string;
}) {
  return <OfficeDialog compact open={open} onClose={onClose} busy={busy} title={title} description={description}
    footer={<button className="button-accent" onClick={onConfirm} disabled={busy}>{busy ? "처리 중…" : confirmLabel}</button>}>
    {children}
  </OfficeDialog>;
}
