# Skyway Blended Discount Rate Calculations

This repository contains scripts to setup and run things for calculating the
blended discount rate for AWS billing products.

## TL;DR

To launch the application:

1. Run `./setup.sh` to setup ClickHouse
2. Run `./run.sh` to run the web application
3. Visit: http://127.0.0.1:5000
  * Click through the interface
  * If there are no clickable links, make sure you're not blocking JavaScript

The links should lead from the main page to: http://127.0.0.1:5000/account/836060457634

And then onto the invoice: http://127.0.0.1:5000/account/836060457634/invoice/156090591

## Scripts

* `setup.sh` - Downloads data, starts ClickHouse, and imports the data into
  clickhouse
* `run.sh` - Runs the web application
* `import_data.py` - called by `setup.sh` to load the data into ClickHouse
* `calculate_blended_discount.py` - script to output the information for the
  terminal
* `web/app.py` - Flask web application

### setup.sh

The `setup.sh` script is used to setup the docker volumes, download the data,
start the ClickHouse server, setup the Python `venv`, install Python
requirements, and then import the test data into ClickHouse.

This script is using Python `venv` because I don't have a lot of experience
starting Python projects from scratch. `venv` seemed like the simplest case,
but I don't have any horses in this race. It works! :)

This script is meant to be idempotent, so it's safe to run multiple times.

### import\_data.py

The `import_data.py` script loads data into the ClickHouse instance `setup.sh`
starts. This script is where manipulations of the ClickHouse schema are done.

It uses `DESCRIBE TABLE file()` to extract the field names and types from the
Parquet dataset to build the DDL necessary to load the data into ClickHouse.
The `INSERT INTO AWSCUR SELECT * FROM file()` query is used to offload the
hard work of loading the data set into the database to ClickHouse. There are
some assumptions: the keys I chose to use as primary keys are not null. This
checked out as a `SELECT count(1) from file()` yielded the same number of rows
as `SELECT count(1) from AWSCUR`. It also assumes the file is a valid Parquet
file. No attempt to check for errors was done in the script.

This script creates two tables:

* `AWSCUR` - The table with the data from the `Parquet` file
* `Discounts` - A table for mapping the discount data from the assigment to
  the `bill_payer_account_id` in the `AWSCUR` table.

#### Table: AWSCUR

The table schema is mostly derived automatically from the field types in the
Parquet file.

The `typeOverrides` dict in the `build_awscur_table()` function provides a
mechanism to override the type on specified fields. This is done to ensure the
`PRIMARY KEY` fields are correctly initialized in the database as `NOT NULL`.

The table is a `MergeTree` table using the primary key:

```
ORDER BY ( bill_payer_account_id, bill_invoice_id, bill_billing_period_end_date, product_servicecode, line_item_usage_end_date )
```

This is based on this assignment, but would likely need to be revised for
wider application. 

The table is partitioned by `bill_payer_account_id,
toYYYYMM(bill_billing_period_end_date)` to put all the data for the same
account in the same partition. The addition of the
`toYYYYMM(bill_billing_period_end_date)` is an optimization should we want to
add expiration of the data via a `TTL`. 

**NOTE:** I did not go too far with optimizations for the ClickHouse data
types and `CODEC`s. This schema ran fast enough to not bother with applying
various `CODEC`s to the columns. However, the `typeOverrides` dict provides a
mechanism for doing so in the future.

For instance, if we wanted to reduce the size further, we could try things
like:

```
typeOverrides = {
    "bill_invoice_id": 'UInt64 CODEC(Delta, ZSTD)',
    "bill_billing_period_end_date": 'DateTime CODEC(Delta, ZSTD)',
    "bill_payer_account_id": 'UInt64 CODEC(Delta, ZSTD)',
    "line_item_usage_end_date": 'DateTime CODEC(DoubleDelta, ZSTD)',
    ...
}
```

Applying a `Delta` or `DoubleDelta` (in some cases) would allow data to be
compressed as date fields appear to increment at 24h or 1 month intervals in
the dataset.  This means a DoubleDelta encoding could potentially normalize
those columns to zeros, *based on the data ordering*.

There might be other optimizations to the schema to afford greater performance
in production. The schema was chosen as an "educated guess" as to where I
would start if I were scaling this for production uses.

#### Table: Discounts

The `Discounts` table is pretty simple. It takes a `bill_payer_account_id` and
`product_servicecode` to map to the `AWSCUR` table. This was done for
simplicity, but there is a pretty obvious shortcut I took. The discounts don't
have a start and end date. The exercise didn't request that level complexity,
but in real life, these rates change and would then need that functionality.

To address this, I would add `not_before` and `not_after` fields to the table.
The query for calculating discount rates would need to consider this
limitation against the `line_item_usage_{start,end}_date` fields during the
discount calculation query. That would make the query significantly more
complex, add this to the JOIN conditional:

```
...
AND AWSCUR.line_item_start_date > Discounts.not_before
AND AWSCUR.line_item_start_data <= Discounts.not_after
AND AWSCUR.line_item_end_date <= Discounts.not_after
```

For the sake of simplicity, I set this table to use the `ReplacingMergeTree`
engine. This means that any duplicate values by the primary key will overwrite
the pre-existing elements. This is helpful because ClickHouse isn't designed
to accomodate `UPDATE` operations. They are possible, but not recommended.
Using a `ReplacingMergeTree` engine is the most "ClickHouse" way to create a
table that will include rows which may be updated.

### calculate\_blended\_discount.py

The `calculate_blended_discount.py` assumes the `bill_payer_account_id` is
`836060457634` and there's only a single invoice in the data set. This was a
safe assumption for the dataset provided.

This script was used to play with the ClickHouse Python bindings and
ClickHouse queries to be used in the web application. It's not necessary for
the web application.

## Web Application

To run the application, either use the provided `./run.sh`, or install the
`requirements.txt` and launch it via `python web/app.py`. From there, you can
then connect to http://127.0.0.1:5000/ to navigate the application.

### Pages

The `/` page displays all the unique account IDs in a list.

Clicking on an account ID takes you to `/account/{{ account_id }}` where
you'll discover a list of invoices.

Clicking on an invoice ID takes you to `/account/{{ account_id }}/invoice/{{
invoice_id }}`. This is the view of requested in the assignment.  The Blended
Discount is listed in a header element in green. Additional details are
provided to provide context for that invoice.

The requirements didn't specifically request this navigation pattern, but it's
a nod to where the application would be headed in production. This affords the
application the ability to view multiple invoices from multiple accounts. This
isn't exactly "ready" for production.

### Terrible Mistakes Made

* The app is not using OpenAPI with doc generation for the API.
* The queries for "accounts" and "invoices" are not limited in anyway.
* The `Discounts` table doesn't currently support start/end dates for
  discounts.
* There is no authentication.
* The rest of the data looks interesting too, but I left it alone.
* The web app looks terrible!

### Notes

The web application consists of a `flask` application with a handful of
templates. Each of the pages loads its content via a JavaScript `fetch(..)` to
the API handlers. There are no JavaScript libraries or frameworks, again to
reduce the complexity and demonstrate my own coding style. I did yank the
`bankers_round(..)` javascript from StackOverflow to save time.

## Disclaimer

No AI was used in the making of this project. I did heavily consult the
internet as I've never built a Python web application before, but the design
and implementation are my own. I am sure the Python could be improved a bit,
but it's not my daily driver, so the code works and is fast, it might not be
stylistically the great Python ever created, though.

Your mileage may vary, subject to availability, apply directly to the head.
