from __future__ import annotations

from app.models import DemoProcess


DEMOS: list[DemoProcess] = [
    DemoProcess(
        id="expense-reimbursement",
        title="Employee Expense Reimbursement Review",
        domain="finance_ops",
        text=(
            "The Finance analyst receives reimbursement requests in Workday with receipt images, "
            "merchant name, amount, currency, expense category, cost center, and business purpose. "
            "The Finance analyst checks that receipts are attached and that each line matches the "
            "travel and expense policy. If receipts are missing or the business purpose is unclear, "
            "the Finance analyst records the rejection reason in Workday and returns the request to "
            "the employee. The Manager approves requests under $500 within 2 business days when the "
            "request matches policy. Finance approves requests from $500 to $2,500 within 2 business "
            "days. The Controller approves requests above $2,500 within 3 business days. Finance "
            "schedules approved reimbursements in Workday for the next payroll run and records an "
            "audit note with source evidence, decision reason, actor, timestamp, and system outcome. "
            "Weekly corrections update the expense policy examples and reason-code checklist."
        ),
    ),
    DemoProcess(
        id="vendor-onboarding",
        title="Vendor Onboarding And Risk Review",
        domain="procurement",
        text=(
            "A business owner submits a new vendor request with company name, tax ID, remittance account "
            "details, contract value, data access level, and service description. Procurement checks "
            "whether the vendor already exists in Coupa. If the vendor is new, procurement sends the "
            "supplier a W-9, remittance validation form, and security questionnaire. Finance verifies "
            "bank details and tax information within 1 business day and records an audit note with source "
            "evidence, decision reason, actor, timestamp, and system outcome. Legal reviews contracts "
            "above $50,000 within 2 business days; if legal rejects the contract, procurement notifies "
            "the business owner and closes the request. Security reviews vendors that handle customer "
            "data within 2 business days; if security rejects the vendor, procurement notifies the "
            "business owner and closes the request. Once all reviews pass, procurement creates the vendor "
            "record in Coupa and records an audit note with source evidence, decision reason, actor, "
            "timestamp, and system outcome. The SOP says emergency bank-detail overrides may be used "
            "during supplier outages, but it does not say who approves the override. Weekly corrections "
            "update risk rules, exception examples, and the onboarding checklist."
        ),
    ),
    DemoProcess(
        id="billing-inquiry-triage",
        title="Customer Billing Inquiry Triage",
        domain="revenue_operations",
        text=(
            "Customer support receives billing inquiries through Zendesk. The support agent confirms "
            "customer identity and subscription status in Stripe. The support agent extracts invoice "
            "number, plan name, billing period, and customer question. If the inquiry matches the "
            "published FAQ, the support agent sends the response template and records the response in "
            "Zendesk. Otherwise the support agent routes the case to the Revenue Operations queue with "
            "the invoice number, customer ID, and source evidence. Revenue Operations responds within "
            "1 business day, records the resolution reason in Zendesk, and closes the case. Revenue Operations "
            "records weekly corrections, and the corrections update the FAQ and routing examples."
        ),
    ),
]


def get_demo(demo_id: str) -> DemoProcess | None:
    return next((demo for demo in DEMOS if demo.id == demo_id), None)
