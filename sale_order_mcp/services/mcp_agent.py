import os
import requests
import json
import google.generativeai as genai


# =========================
# KONFIGURASI
# =========================
# API Key Gemini bisa di-set via environment variable atau langsung di sini
# Untuk set env var: set GEMINI_API_KEY=your_api_key_here (Windows)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

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

    def __init__(self, odoo: OdooClient, gemini_api_key: str = ""):
        self.odoo = odoo
        self.gemini_api_key = gemini_api_key

    # -------------------------
    # INTENT ROUTER
    # -------------------------
    def run(self, text: str):

        text_lower = text.lower()

        # Intent: invoice SO yang belum done / belum selesai
        if ("invoice" in text_lower and "belum" in text_lower and ("done" in text_lower or "selesai" in text_lower)):
            return self.get_invoices_not_done()

        # Intent: SO yang belum ada invoice-nya
        if "sale order" in text_lower and "belum" in text_lower and "invoice" in text_lower:
            return self.get_so_without_invoice()

        # Intent: invoice belum bayar
        if "invoice" in text_lower and "belum bayar" in text_lower:
            return self.get_unpaid_invoices()

        # Fallback: gunakan Gemini AI untuk menganalisis prompt
        return self.search_by_genai(text)

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

    # -------------------------
    # TOOL 4: Search by Gemini AI
    # -------------------------
    def search_by_genai(self, user_prompt: str):
        """
        Gunakan Gemini AI untuk menganalisis prompt user,
        ambil data relevan dari Odoo, lalu berikan jawaban.
        """
        if not self.gemini_api_key:
            return {
                "error": "API Key Gemini belum diatur. "
                         "Set environment variable GEMINI_API_KEY atau isi langsung di kode."
            }

        # 1. Ambil data dari Odoo untuk konteks AI
        try:
            # Ambil draft invoices
            draft_invoices = self.odoo.execute(
                "account.move",
                "search_read",
                [[('move_type', '=', 'out_invoice')]],
                {"fields": ["name", "partner_id", "amount_total", "state",
                            "payment_state", "invoice_origin"], "limit": 50}
            )

            # Ambil sale orders
            sale_orders = self.odoo.execute(
                "sale.order",
                "search_read",
                [[('state', 'in', ['sale', 'done'])]],
                {"fields": ["name", "partner_id", "amount_total", "state",
                            "invoice_status"], "limit": 50}
            )
        except Exception as e:
            return {"error": f"Gagal mengambil data dari Odoo: {str(e)}"}

        # 2. Konfigurasi Gemini SDK
        genai.configure(api_key=self.gemini_api_key)

        # 3. Buat model Gemini
        model = genai.GenerativeModel('gemini-2.0-flash')

        # 4. Susun prompt dengan konteks data Odoo
        ai_prompt = f"""
        Kamu adalah asisten ERP Odoo yang cerdas. Berikut adalah data dari sistem Odoo:

        === DATA INVOICE ===
        {json.dumps(draft_invoices, indent=2, default=str)}

        === DATA SALE ORDER ===
        {json.dumps(sale_orders, indent=2, default=str)}

        Berdasarkan data di atas, jawab pertanyaan berikut dengan ringkas dan jelas:
        Pertanyaan: {user_prompt}

        Berikan jawaban dalam format yang mudah dibaca. Jika ada data tabel, gunakan format tabel.
        Jawab dalam bahasa yang sama dengan pertanyaan user.
        """

        try:
            # 5. Kirim prompt ke Gemini dan kembalikan hasilnya
            response = model.generate_content(ai_prompt)
            return {"ai_response": response.text}
        except Exception as e:
            return {"error": f"Terjadi kesalahan saat menghubungi API Gemini: {str(e)}"}

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

agent = OdooMCPAgent(odoo_client, gemini_api_key=GEMINI_API_KEY)


@mcp.tool()
def query_erp(natural_language: str) -> str:
    """
    Natural language interface ke Odoo ERP.
    Contoh prompt:
    - "invoice SO yang belum done"
    - "sale order yang belum invoice"
    - "invoice belum bayar"
    - atau pertanyaan apapun tentang data ERP (akan diproses oleh Gemini AI)
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