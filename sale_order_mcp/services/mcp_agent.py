import requests
import json

class OdooClient:
    def __init__(self, url, db, user, password):
        self.url = url
        self.db = db
        self.user = user
        self.password = password
        self.uid = None  # lazy auth

    def _authenticate(self):
        try:
            res = requests.post(f"{self.url}/jsonrpc", json={
                "jsonrpc": "2.0",
                "method": "call",
                "params": {
                    "service": "common",
                    "method": "login",
                    "args": [self.db, self.user, self.password]
                },
                "id": 1
            }).json()

            uid = res.get("result")
            if not uid:
                raise Exception(f"Login gagal, response: {res}")
            return uid
        except requests.exceptions.ConnectionError:
            raise Exception(f"Tidak bisa konek ke Odoo di {self.url}")

    def _ensure_auth(self):
        """Lazy authentication - hanya login saat pertama kali dipanggil"""
        if self.uid is None:
            self.uid = self._authenticate()

    def execute(self, model, method, args, kwargs=None):
        self._ensure_auth()
        kwargs = kwargs or {}

        res = requests.post(f"{self.url}/jsonrpc", json={
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": "object",
                "method": "execute_kw",
                "args": [
                    self.db,
                    self.uid,
                    self.password,
                    model,
                    method,
                    args,
                    kwargs
                ]
            },
            "id": 2
        }).json()

        if "error" in res:
            raise Exception(f"Odoo error: {res['error']}")

        return res["result"]


# =========================
# MCP AGENT CORE
# =========================

class OdooMCPAgent:

    def __init__(self, odoo: OdooClient):
        self.odoo = odoo

    # -------------------------
    # INTENT ROUTER
    # -------------------------
    def run(self, text: str):

        text = text.lower()

        # Intent: invoice SO yang belum done / belum selesai
        if ("invoice" in text and "belum" in text and ("done" in text or "selesai" in text)):
            return self.get_invoices_not_done()

        # Intent: SO yang belum ada invoice-nya
        if "sale order" in text and "belum" in text and "invoice" in text:
            return self.get_so_without_invoice()

        # Intent: invoice belum bayar
        if "invoice" in text and "belum bayar" in text:
            return self.get_unpaid_invoices()

        return {"error": f"Intent tidak dikenali dari: '{text}'. "
                f"Coba gunakan kata kunci seperti: "
                f"'invoice SO belum done', 'sale order belum invoice', 'invoice belum bayar'"}

    # -------------------------
    # TOOL 1: Invoice SO yang belum done
    # -------------------------
    def get_invoices_not_done(self):
        """Cari invoice dari SO yang statusnya belum 'posted' (done)"""
        return self.odoo.execute(
            "account.move",
            "search_read",
            [[
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'draft'),
            ]],
            {"fields": ["name", "partner_id", "amount_total", "state", "invoice_origin"]}
        )

    # -------------------------
    # TOOL 2: SO yang belum punya invoice
    # -------------------------
    def get_so_without_invoice(self):

        return self.odoo.execute(
            "sale.order",
            "search_read",
            [[('invoice_ids', '=', False), ('state', '=', 'sale')]],
            {"fields": ["name", "partner_id", "amount_total", "state"]}
        )

    # -------------------------
    # TOOL 3: Invoice belum bayar
    # -------------------------
    def get_unpaid_invoices(self):

        return self.odoo.execute(
            "account.move",
            "search_read",
            [[
                ('move_type', '=', 'out_invoice'),
                ('payment_state', 'in', ['not_paid', 'partial'])
            ]],
            {"fields": ["name", "partner_id", "amount_residual", "state", "payment_state"]}
        )


# =========================
# FASTMCP WRAPPER
# =========================

from fastmcp import FastMCP

mcp = FastMCP("odoo-mcp")


odoo_client = OdooClient(
    url="http://localhost:8069",
    db="odoo_mcp1",
    user="admin",
    password="admin"
)

agent = OdooMCPAgent(odoo_client)


@mcp.tool()
def query_erp(natural_language: str) -> str:
    """
    Natural language interface ke Odoo ERP.
    Contoh prompt:
    - "invoice SO yang belum done"
    - "sale order yang belum invoice"
    - "invoice belum bayar"
    """
    try:
        result = agent.run(natural_language)
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


# =========================
# RUN SERVER
# =========================
if __name__ == "__main__":
    print("Starting MCP Server pada http://localhost:8000/mcp")
    mcp.run(transport="streamable-http", port=8000)