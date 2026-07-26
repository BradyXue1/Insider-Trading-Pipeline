import os
os.environ["POLARS_SKIP_CPU_CHECK"] = "1"
import polars as pl

q = (
    pl.scan_csv("7_25_26_insider_data.csv")
)
df=q.collect()
print(df.columns)
'''
q = (
    pl.scan_csv("cleaned_insider_data.csv")
)
df=q.collect()
print(df.columns)
df=df.with_columns(
    (pl.col("price_purchased_at")*100/pl.col("price_trade_day")-100).alias("price_discrepancy_%")
)
workspace=df.select(
    pl.col("insider_name"),
    pl.col("is_purchase"),
    pl.col("net_shares"),
    pl.col("net_value"),
    pl.col("position"),
    pl.col("ticker"),
    pl.col("transaction_date"),
    pl.col("price_trade_day"),
    pl.col("price_purchased_at")
)
final=df.filter(
    (pl.col("net_value").abs() > 0) &
    (pl.col("price_discrepancy_%").abs() < 20) &
    (
        ((pl.col("is_purchase") == True) & (pl.col("net_shares") > 0) & (pl.col("net_value") > 0)) |
        ((pl.col("is_purchase") == False) & (pl.col("net_shares") < 0) & (pl.col("net_value") < 0))
    )
)
print(final)
final.write_csv("7_25_26_insider_data.csv")
'''
