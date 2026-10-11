export type PromotionReceipt = {
  id: string; source_digest: string; confirmed_version: number; status: string;
};

export function canPromote(receipt: PromotionReceipt, permissions: readonly string[]): boolean {
  return receipt.status === "CONFIRMED" && ["import.confirm", "transaction.create"].every(permission => permissions.includes(permission));
}

export function promotionCommand(receipt: PromotionReceipt) {
  return { expected_version: receipt.confirmed_version, receipt_id: receipt.id, source_digest: receipt.source_digest };
}
