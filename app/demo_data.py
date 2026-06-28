from __future__ import annotations

from app.models import DemoProcess


DEMOS: list[DemoProcess] = [
    DemoProcess(
        id="invoice-exceptions",
        title="Invoice Exception Resolution",
        domain="accounts_payable",
        text=(
            "When an invoice arrives, the AP analyst logs it in NetSuite and extracts vendor name, "
            "invoice number, PO number, amount, currency, tax, and due date. The analyst checks the "
            "vendor master record and compares the invoice against the purchase order and receiving "
            "record. If the invoice matches within tolerance, the AP analyst routes it to the finance "
            "queue for approval. Invoices above $25,000 require controller approval. If the supplier "
            "has changed bank details, the AP analyst emails procurement to confirm the update before "
            "payment. If the PO is missing, the analyst asks the requester for the right PO. If the "
            "requester does not respond, the invoice remains pending. Approved invoices are scheduled "
            "for payment in the next payment run. Payment confirmation is recorded in NetSuite. The "
            "current SOP does not define a timeout for approvals, a rejection path after controller "
            "review, or a required audit note for bank-detail changes."
        ),
    ),
    DemoProcess(
        id="vendor-onboarding",
        title="Vendor Onboarding And Risk Review",
        domain="procurement",
        text=(
            "A business owner submits a new vendor request with company name, tax ID, banking details, "
            "contract value, and service description. Procurement checks whether the vendor already "
            "exists in Coupa. If the vendor is new, procurement sends the supplier a W-9 and security "
            "questionnaire. Finance verifies bank details and tax information. Legal reviews contracts "
            "above $50,000. Security reviews vendors that handle customer data. Once all reviews pass, "
            "procurement creates the vendor record and notifies the business owner. The SOP says urgent "
            "vendors may be fast-tracked by the team, but it does not say who approves the fast track, "
            "how exceptions are logged, or what happens when security rejects a vendor."
        ),
    ),
    DemoProcess(
        id="refund-approval",
        title="Customer Refund Approval",
        domain="revenue_operations",
        text=(
            "Customer support receives refund requests through Zendesk. The support agent confirms the "
            "customer identity, checks subscription status in Stripe, and reviews the reason for the "
            "refund. Refunds under $250 can be approved by support if the customer is within the refund "
            "policy window. Refunds between $250 and $2,000 require revenue operations approval. Refunds "
            "above $2,000 require finance approval. If the customer disputes the policy, the request is "
            "sent to a manager. Approved refunds are processed in Stripe and the customer is notified. "
            "The policy does not specify SLA for manager review, evidence requirements for disputes, "
            "or how duplicate refund requests should be detected."
        ),
    ),
]


def get_demo(demo_id: str) -> DemoProcess | None:
    return next((demo for demo in DEMOS if demo.id == demo_id), None)
