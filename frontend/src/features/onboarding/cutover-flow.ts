import type { CutoverStatus } from "./model";

export type CutoverPhase = "NO_OPENING" | "CREATE_JOURNAL" | "POST_JOURNAL" | "PREVIEW_BLOCKED" | "PROMOTE" | "COMPLETE";

export function cutoverPhase(status: CutoverStatus): CutoverPhase {
  if (status.no_opening_balance) return "NO_OPENING";
  if (!status.journal_id) return "CREATE_JOURNAL";
  if (status.journal_status !== "POSTED") return "POST_JOURNAL";
  if (!status.ar_ap_source_present || status.ar_ap_promoted) return "COMPLETE";
  return status.ar_ap_preview_ready ? "PROMOTE" : "PREVIEW_BLOCKED";
}

export function canPromoteCutover(status: CutoverStatus, permissions: string[]) {
  return permissions.includes("journal.propose") && status.ar_ap_totals.every(total =>
    permissions.includes(total.role === "AR" ? "collection.record" : "payment.record"));
}
