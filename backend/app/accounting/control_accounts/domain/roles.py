from enum import StrEnum


class ControlAccountRole(StrEnum):
    AR = "AR"
    AP = "AP"
    TAX_INPUT = "TAX_INPUT"
    TAX_OUTPUT = "TAX_OUTPUT"
    BANK_CASH = "BANK_CASH"
    CARD_CLEARING = "CARD_CLEARING"
    CARD_PAYABLE = "CARD_PAYABLE"


ROLE_ACCOUNT_TYPE = {
    ControlAccountRole.AR: "ASSET",
    ControlAccountRole.AP: "LIABILITY",
    ControlAccountRole.TAX_INPUT: "ASSET",
    ControlAccountRole.TAX_OUTPUT: "LIABILITY",
    ControlAccountRole.BANK_CASH: "ASSET",
    ControlAccountRole.CARD_CLEARING: "ASSET",
    ControlAccountRole.CARD_PAYABLE: "LIABILITY",
}
