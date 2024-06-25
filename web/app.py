from flask import Flask, render_template
from flask_restful import Api, Resource
import clickhouse_connect
import json

app = Flask(__name__)
api = Api(app, prefix='/api')

## Query Definitions
invoice_product_query = """\
SELECT
    if(empty(product_servicecode), product_product_name, product_servicecode) as product_servicecode,
    sum(line_item_unblended_cost) AS total,
    sum(line_item_unblended_cost * (1 - coalesce(discount, 0))) AS discounted
FROM AWSCUR
LEFT JOIN Discounts ON
    (AWSCUR.bill_payer_account_id = Discounts.bill_payer_account_id)
    AND (AWSCUR.product_servicecode = Discounts.product_servicecode)
WHERE (bill_invoice_id = {invoice_id:UInt64})
    AND (line_item_line_item_type = 'Usage')
GROUP BY product_servicecode
HAVING total > 0
ORDER BY product_servicecode ASC
"""
blended_calc_query = """\
SELECT
    sum(total) AS undiscounted_total,
    sum(discounted) AS discounted_total,
    1 - (sum(discounted) / sum(total)) AS blended_discount_rate
FROM ProductSummary
"""

## Non-API Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/account/<int:account_id>')
def account(account_id):
    return render_template('account.html', account_id=account_id)

@app.route('/account/<int:account_id>/invoice/<int:invoice_id>')
def account_invoice(account_id, invoice_id):
    return render_template('account_invoice.html', account_id=account_id, invoice_id=invoice_id)

## API Resources
class Accounts(Resource):
    def get(self):
        db  = clickhouse_connect.get_client()
        res = db.query("""\
                SELECT
                    bill_payer_account_id as account_id
                FROM AWSCUR
                GROUP BY bill_payer_account_id
                """)
        accounts = {}
        for account in res.named_results():
            accounts[account['account_id']] = account
        return accounts

class Invoices(Resource):
    def get(self, account_id):
        db  = clickhouse_connect.get_client()
        res = db.query("""\
            SELECT
                bill_invoice_id as invoice_id,
                max(bill_billing_period_end_date) as end_date
            FROM AWSCUR
            WHERE bill_payer_account_id = {account_id:UInt64}
            GROUP BY invoice_id
            ORDER BY end_date DESC
            """,
            parameters={"account_id": account_id}
        )

        invoices = []
        for row in res.named_results():
            row['end_date'] = row['end_date'].strftime('%Y-%m-%d')
            invoices.append(row)

        return invoices

class InvoiceProducts(Resource):
    def get(self, invoice_id):
        db  = clickhouse_connect.get_client()
        res = db.query(invoice_product_query,
            parameters={"invoice_id": invoice_id}
        )

        products={}
        for product in res.named_results():
            products[product['product_servicecode']] = {
                'undiscounted_total': product['total'],
                'discounted_total': product['discounted'],
            }

        return { "invoice_id": invoice_id, "products": products }

class InvoiceTotals(Resource):
    def get(self, invoice_id):
        db    = clickhouse_connect.get_client()
        query = f"WITH ProductSummary AS ({invoice_product_query})" + blended_calc_query
        res   = db.query(query,
            parameters={"invoice_id": invoice_id}
        )

        return list(res.named_results())[0]

## API Resource Routes
api.add_resource(Accounts, '/accounts')
api.add_resource(Invoices, '/invoices/<int:account_id>')
api.add_resource(InvoiceProducts, '/invoice/<int:invoice_id>/products')
api.add_resource(InvoiceTotals,   '/invoice/<int:invoice_id>/totals')

if __name__ == '__main__':
    app.run(debug=True)
