import clickhouse_connect

client = clickhouse_connect.get_client()

account_id = 836060457634

bill_summary_query = f"""
SELECT
    if(empty(product_servicecode), product_product_name, product_servicecode) as product_servicecode,
    sum(line_item_unblended_cost) AS total,
    sum(line_item_unblended_cost * (1 - coalesce(discount, 0))) AS discounted
FROM AWSCUR
LEFT JOIN Discounts ON
    (AWSCUR.bill_payer_account_id = Discounts.bill_payer_account_id)
    AND (AWSCUR.product_servicecode = Discounts.product_servicecode)
WHERE (bill_payer_account_id = {account_id})
    AND (line_item_line_item_type = 'Usage')
GROUP BY product_servicecode
HAVING total > 0
ORDER BY product_servicecode ASC
"""

blended_calc_query = f"""
WITH BillSummary AS ({bill_summary_query})
SELECT
    sum(total) AS Unblended,
    sum(discounted) AS Discounted,
    1 - (sum(discounted) / sum(total)) AS Blended
FROM BillSummary
"""

header_template = "   {0:30}   {1:>10}   {2:10}"
cols = [ 'Product', 'Total', 'Discounted' ]
divs = [ "-" * 30, "-" * 10, "-" * 10 ]
products = [
        header_template.format(cols[0], cols[1], cols[2]),
        header_template.format(divs[0], divs[1], divs[2]),
]
res = client.query(bill_summary_query)
for product in res.named_results():
    text = f"   {product['product_servicecode']:30}  ${round(product['total'],2):10}  ${round(product['discounted'],2):10}"
    products.append(text)

res = list(client.query(blended_calc_query).named_results())[0]
summary = f"""Account ID: {account_id}

Billing Summary:

{"\n".join(products)}

Billing Totals:

    Undiscounted: ${round(res['Unblended'],2)}
      Discounted: ${round(res['Discounted'],2)}

Blended Discount: {round(100.0 * res['Blended'],2)}%"""
print(summary)
