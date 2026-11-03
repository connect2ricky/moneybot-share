import re

UNCATEGORISED = "Uncategorised"
SELF_TRANSFER = "Self transfer"

# group decides how a category is counted: expense, income, savings, or transfer (ignored).
CATEGORIES = {
    "Groceries": "expense",
    "Food & Dining": "expense",
    "Shopping": "expense",
    "Fuel & Transport": "expense",
    "Bills & Utilities": "expense",
    "Mobile & Internet": "expense",
    "Rent": "expense",
    "Loan EMI": "expense",
    "Credit card bills": "expense",
    "Health": "expense",
    "Personal care": "expense",
    "Entertainment": "expense",
    "Family & Friends": "expense",
    "Education": "expense",
    "Travel": "expense",
    "Baby": "expense",
    "Supplements": "expense",
    "Digital & Subscriptions": "expense",
    "Drinking": "expense",
    "Mom": "expense",
    "Other": "expense",
    UNCATEGORISED: "expense",
    "Salary": "income",
    "Interest": "income",
    "Other income": "income",
    "Savings & Investments": "savings",
    SELF_TRANSFER: "transfer",
    "Ignored": "transfer",
}

# First match wins; matched against "PAYEE | INFO" in upper case.
RULES = [
    # Add your own people first, for example: (r"RAVI KUMAR", "Family & Friends"),
    (r"BY SAL|SALARY", "Salary"),
    (r"INT\.PD|INTEREST", "Interest"),
    (r"_EMI_|LIC ?HOUSING|HOME LOAN", "Loan EMI"),
    (r"\bCRED\b", "Credit card bills"),
    (r"JUPITER POT|APSPL|GROWW|ZERODHA|INDMONEY|MUTUAL FUND|\bSIP\b", "Savings & Investments"),
    (r"DISTRICT|PVR|INOX|BOOKMYSHOW", "Entertainment"),
    (r"BLINKIT|GROCER|BAZAAR|DMART|SUPER ?MARK|ZEPTO|BIGBASKET|INSTAMART|CHICKEN|KIRANA", "Groceries"),
    (r"ZOMATO|SWIGGY|HOTEL|FOOD|CHAI|RESTAURANT|CAFE|BAKERY|BIRYANI|TIFFIN", "Food & Dining"),
    (r"ANTHROPIC|NETFLIX|SPOTIFY|APPLE MED|YOUTUBE|HOTSTAR|OPENAI", "Digital & Subscriptions"),
    (r"AMAZON|MYNTRA|FLIPKART|AJIO|LG ELECTRONICS|MEESHO", "Shopping"),
    (r"FILLING|PETROL|FUEL|HPCL|IOCL|BPCL|UBER|\bOLA\b|RAPIDO|METRO|PUNCHER|FASTAG", "Fuel & Transport"),
    (r"IRCTC|MAKEMYTRIP|REDBUS|INDIGO|CLEARTRIP", "Travel"),
    (r"JIO|AIRTEL|ACT FIBER|ATRIA CONVERGENCE|VODAFONE", "Mobile & Internet"),
    (r"ELECTRICITY|SPDCL|POWER DISTRIBUTION|HP GAS|BHARAT CONNECT|LPG|WATER BOARD", "Bills & Utilities"),
    (r"PHARM|MEDICAL|HOSPITAL|APOLLO|CLINIC|NUTRITION|DIAGNOSTIC", "Health"),
    (r"NATURALS|SALON|SALOON", "Personal care"),
]
_COMPILED = [(re.compile(p), c) for p, c in RULES]


def payee_key(payee: str) -> str:
    return " ".join((payee or "").upper().split())


def by_rules(payee: str, info: str) -> str:
    text = f"{payee} | {info}".upper()
    for pattern, category in _COMPILED:
        if pattern.search(text):
            return category
    return UNCATEGORISED
