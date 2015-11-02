# check_dynamodb_capacity.py

Nagios plugin to check DynamoDB consumed capacity

## Install

```
pip install -r requirements.txt
python check_dynamodb_capacity.py --help
```

## Sample usage

Check dynamodb_table consumed capacity. By default the last hour will be
checked. The script will return warning if table consumed 70% of the assigned
capacity for more than 25% of the specified timedelta. The default timedelta
is 60 min, so the 25% of one hour is 15min.

The check will return critical if consumed capacity was more than 85% for more
than 25% of the specified time.

```
python check_dynamodb_capacity.py dynamodb_table
```

Check dynamodb_table consumed capacity and return critical if table consumed
more than 85% for more than the 50% of the specified timedelta:

```
python check_dynamodb_capacity.py -c 85%:50% dynamodb_table
```

Check dynamodb_table consumed write capacity instead of read.

```
python check_dynamodb_capacity.py -C read dynamodb_table
```

Check dynamodb_table consumed read capacity for a specified index.

```
python check_dynamodb_capacity.py --index index_name dynamodb_table
```
