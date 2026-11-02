"""Bank housing loans: reference schemes + an interactive financing plan.

Caps and rates change often, so every scheme carries `as_of` and a note to verify with the
bank, and the UI lets the user override cap/rate/term. Numbers here are defaults, not quotes.
"""
from dataclasses import dataclass, field
from typing import Optional

AS_OF = "پاییز ۱۴۰۵ (تقریبی)"
BIG_CITIES = {"کرج", "مشهد", "اصفهان", "تبریز", "شیراز", "اهواز", "قم"}

# caps in toman per city tier: tehran / big (>200k pop. metropolises) / other
LOANS = [
    {
        "id": "maskan-yekom",
        "bank": "بانک مسکن",
        "name": "صندوق پس‌انداز مسکن یکم",
        "caps": {"tehran": 480_000_000, "big": 400_000_000, "other": 320_000_000},
        "couple_multiplier": 1.0,
        "rate": 18.0,
        "years": 12,
        "first_home_only": True,
        "requirement": "سپرده‌گذاری حداقل یک سال در حساب مسکن یکم؛ فقط برای خانه اول.",
        "bond_cost_ratio": 0.0,
    },
    {
        "id": "taseh",
        "bank": "بانک مسکن",
        "name": "اوراق تسهیلات مسکن (تسه)",
        "caps": {"tehran": 240_000_000, "big": 200_000_000, "other": 160_000_000},
        "couple_multiplier": 2.0,
        "rate": 18.0,
        "years": 12,
        "first_home_only": False,
        "requirement": "خرید اوراق تسه از بورس به میزان سقف وام؛ زوجین هر کدام جداگانه وام می‌گیرند.",
        "bond_cost_ratio": 0.25,
    },
    {
        "id": "javani",
        "bank": "بانک‌های عامل",
        "name": "وام مسکن قانون جوانی جمعیت",
        "caps": {"tehran": 300_000_000, "big": 250_000_000, "other": 200_000_000},
        "couple_multiplier": 1.0,
        "rate": 4.0,
        "years": 20,
        "first_home_only": True,
        "child_required": True,
        "requirement": "برای خانواده‌های دارای فرزند متولد شده از سال ۱۴۰۰ به بعد؛ ثبت‌نام در سامانه و نوبت‌دهی.",
        "bond_cost_ratio": 0.0,
    },
    {
        "id": "commercial",
        "bank": "بانک‌های تجاری و خصوصی",
        "name": "تسهیلات خرید مسکن با سپرده (طرح‌های بانکی)",
        "caps": {"tehran": 500_000_000, "big": 400_000_000, "other": 300_000_000},
        "couple_multiplier": 1.0,
        "rate": 23.0,
        "years": 5,
        "first_home_only": False,
        "requirement": "معمولاً معادل چند برابر میانگین موجودی حساب پس از چند ماه؛ شرایط هر بانک متفاوت است.",
        "bond_cost_ratio": 0.0,
    },
]


def city_tier(city: str) -> str:
    if city == "تهران":
        return "tehran"
    return "big" if city in BIG_CITIES else "other"


def monthly_installment(principal: float, annual_rate: float, years: int) -> int:
    n = max(int(years * 12), 1)
    r = annual_rate / 100 / 12
    if r == 0:
        return round(principal / n)
    return round(principal * r / (1 - (1 + r) ** -n))


@dataclass
class LoanOverride:
    id: str
    selected: bool = True
    amount: Optional[int] = None
    rate: Optional[float] = None
    years: Optional[int] = None


@dataclass
class PlanRequest:
    price: int
    savings: int = 0
    monthly_income: int = 0
    city: str = "تهران"
    married: bool = False
    has_child: bool = False
    first_home: bool = True
    loans: list[LoanOverride] = field(default_factory=list)


def loan_catalog(city: str = "تهران", married: bool = False) -> dict:
    tier = city_tier(city)
    items = []
    for loan in LOANS:
        cap = loan["caps"][tier] * (loan["couple_multiplier"] if married else 1)
        items.append({**loan, "default_amount": int(cap), "tier": tier})
    return {"loans": items, "as_of": AS_OF,
            "disclaimer": "سقف و نرخ‌ها تقریبی است و مرتب تغییر می‌کند؛ پیش از تصمیم از شعبه بانک استعلام بگیرید."}


def _eligibility(loan: dict, req: PlanRequest) -> list[str]:
    issues = []
    if loan.get("first_home_only") and not req.first_home:
        issues.append("فقط برای خرید خانه اول")
    if loan.get("child_required") and not req.has_child:
        issues.append("نیاز به فرزند متولد ۱۴۰۰ به بعد")
    return issues


def build_plan(req: PlanRequest) -> dict:
    overrides = {o.id: o for o in req.loans}
    catalog = {l["id"]: l for l in loan_catalog(req.city, req.married)["loans"]}
    rows, total_loan, total_inst, bond_cost = [], 0, 0, 0
    for lid, loan in catalog.items():
        o = overrides.get(lid, LoanOverride(id=lid, selected=False))
        issues = _eligibility(loan, req)
        amount = int(o.amount if o.amount is not None else loan["default_amount"])
        cap_warning = amount > loan["default_amount"]
        rate = o.rate if o.rate is not None else loan["rate"]
        years = o.years or loan["years"]
        inst = monthly_installment(amount, rate, years)
        used = o.selected and not issues and amount > 0
        row = {
            "id": lid, "name": loan["name"], "bank": loan["bank"], "selected": used,
            "eligible": not issues, "issues": issues, "amount": amount, "rate": rate, "years": years,
            "monthly_installment": inst, "total_repayment": inst * years * 12,
            "total_interest": inst * years * 12 - amount,
            "bond_cost": int(amount * loan["bond_cost_ratio"]),
            "cap_warning": cap_warning,
        }
        rows.append(row)
        if used:
            total_loan += amount
            total_inst += inst
            bond_cost += row["bond_cost"]
    # Bond purchase is paid in cash up front, so it eats into savings.
    gap = max(req.price - total_loan - max(req.savings - bond_cost, 0), 0)
    dti = round(total_inst / req.monthly_income * 100, 1) if req.monthly_income else None
    if dti is None:
        advice = "درآمد ماهانه را وارد کنید تا توان بازپرداخت سنجیده شود."
    elif dti <= 30:
        advice = "قسط‌ها کمتر از ۳۰٪ درآمد است؛ بازپرداخت معقول به نظر می‌رسد."
    elif dti <= 45:
        advice = "قسط‌ها بین ۳۰ تا ۴۵٪ درآمد است؛ فشار مالی قابل‌توجه است."
    else:
        advice = "قسط‌ها بیش از ۴۵٪ درآمد است؛ بانک ممکن است نپذیرد و ریسک بالاست."
    return {
        "loans": rows,
        "total_loan": total_loan,
        "total_monthly_installment": total_inst,
        "bond_cost": bond_cost,
        "loan_share_pct": round(total_loan / req.price * 100, 1) if req.price else 0,
        "gap": gap,
        "debt_to_income_pct": dti,
        "advice": advice,
        "as_of": AS_OF,
        "warnings": [
            "سقف، نرخ و شرایط وام‌ها تقریبی‌اند و باید از بانک استعلام شوند.",
            "هزینه‌های معامله مانند کمیسیون، مالیات و دفترخانه در کسری بودجه محاسبه نشده‌اند.",
        ],
    }
