#!python3

import clickhouse_connect
import time

client = clickhouse_connect.get_client()

def build_awscur_table():
    result = client.query("DESCRIBE TABLE file('AWSCUR.snappy.parquet', Parquet)")
    typeOverrides = {
        "bill_invoice_id": 'UInt64',
        "bill_billing_period_end_date": 'DateTime',
        "bill_billing_period_start_date": 'DateTime',
        "bill_payer_account_id": 'UInt64',
        "line_item_usage_end_date": 'DateTime',
        "line_item_usage_start_date": 'DateTime',
        "product_servicecode": 'LowCardinality(String)',
    }

    columns = []
    for row in result.result_rows:
        col_name = row[0]
        col_type = typeOverrides[col_name] if col_name in typeOverrides else row[1]
        columns.append("{n} {t}".format(n=col_name, t=col_type))

    client.command("""\
    CREATE TABLE IF NOT EXISTS AWSCUR (
    {tableColumns}
    )
    ENGINE=MergeTree()
    ORDER BY ( bill_payer_account_id, bill_invoice_id, bill_billing_period_end_date, product_servicecode, line_item_usage_end_date )
    PARTITION BY ( bill_payer_account_id, toYYYYMM(bill_billing_period_end_date) )
    """.format(tableColumns=",\n".join(columns)))
    print("created AWSCUR table")
    # NOTE: Using TRUNCATE here because 'CREATE OR REPLACE' threw fatal errors on the second run
    client.command("TRUNCATE TABLE AWSCUR")
    start = time.time()
    res = client.command("INSERT INTO AWSCUR SELECT * FROM file('AWSCUR.snappy.parquet', Parquet)")
    elapsed = time.time() - start
    print(f" + loaded data {res.written_rows} rows into AWSCUR in {elapsed:.2f}s")

def build_discounts_table():
    client.command("""\
    CREATE TABLE IF NOT EXISTS Discounts (
        bill_payer_account_id UInt64,
        product_servicecode LowCardinality(String),
        discount Float32
    ) ENGINE=ReplacingMergeTree()
    ORDER BY (bill_payer_account_id, product_servicecode)
    """)
    print("created discounts table")

    discounts = [
        [ 836060457634, 'AmazonS3', 0.12],
        [ 836060457634, 'AmazonEC2', 0.5],
        [ 836060457634, 'AWSDataTransfer', 0.3],
        [ 836060457634, 'AWSGlue', 0.05],
        [ 836060457634, 'AmazonGuardDuty', 0.75],
    ]
    # NOTE: Table is replacing merge tree, so we can reinsert data with the same primary key
    client.insert('Discounts', discounts, column_names=['bill_payer_account_id', 'product_servicecode', 'discount'])
    print(f" + added {len(discounts)} rows into Discounts")
    # NOTE: Optimize table or queries might need to use FINAL to collapse the rows
    client.command("OPTIMIZE TABLE Discounts")
    print("  + Discounts table optimized")


build_awscur_table()
build_discounts_table()
