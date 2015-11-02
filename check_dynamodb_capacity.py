#! /usr/bin/env python
# -*- coding: utf-8 -*-
# vim:fenc=utf-8
#
# Copyright © 2015 Carles Amigó <carles.amigo@socialpoint.es>
#
# Distributed under terms of the MIT license.

"""
Nagios plugin to check DynamoDB consumed capacity
"""

from __future__ import print_function
import sys
import argparse
import boto.ec2.cloudwatch
import datetime
import pandas as pd

NAGIOS_STATUSES = {
    'OK': 0,
    'WARNING': 1,
    'CRITICAL': 2,
    'UNKNOWN': 3
}


def main():

    CAPACITY_METRIC = {'read':
                       {'consumed': 'ConsumedReadCapacityUnits',
                        'provisioned': 'ProvisionedReadCapacityUnits',
                        },
                       'write':
                       {'consumed': 'ConsumedWriteCapacityUnits',
                        'provisioned': 'ProvisionedWriteCapacityUnits',
                        },
                       'read_index':
                       {'consumed': 'ConsumedReadCapacityUnits',
                        'provisioned': 'ProvisionedReadCapacityUnits',
                        },
                       'write_index':
                       {'consumed': 'ConsumedWriteCapacityUnits',
                        'provisioned': 'ProvisionedWriteCapacityUnits',
                        },
                       }

    argp = argparse.ArgumentParser(description=__doc__)
    argp.add_argument('table',
                      help='Table to get the metric from.')
    argp.add_argument('-R', '--region', default='us-east-1',
                      help='The AWS region to read metrics from. Default: \
                              %(default)s')
    argp.add_argument('-w', '--warning', default='70%:25%',
                      help='Capacity warning threshold. It has two values \
                              separated by a colon \':\'. The first value \
                              specifies the warning threshold. It can be \
                              specified as an integer or as a percentage. The \
                              second value specifies how many values need to \
                              be over the threshold to trigger a warning. It \
                              can also be specified as an integer or as a \
                              percentage. A warning will be triggered if the \
                              used capacity is over the specified threshold \
                              for more than the specified period. \
                              Default: %(default)s')
    argp.add_argument('-c', '--critical', default='85%:25%',
                      help='Capacity critical threshold. See the warning \
                              definition for details on how it works. \
                              Default: %(default)s')
    argp.add_argument('-p', '--period', default=60, type=int,
                      help='The granularity, in seconds, of the returned \
                              datapoints. period must be at least 60 seconds \
                              and must be a multiple of 60. Default: \
                              %(default)s.')
    argp.add_argument('-t', '--timedelta', default=60, type=int,
                      help='Period in minutes to extract the data. Default: \
                              %(default)s')
    argp.add_argument('-C', '--capacity', default='read',
                      choices=CAPACITY_METRIC.keys(),
                      help='The capacity metric to evaluate. Default: \
                              %(default)s')
    argp.add_argument('-i', '--index',
                      help='If index capacity is evaluated, the index name \
                              needs to be specified')
    argp.add_argument('-d', '--debug', action='store_true',
                      help='Enable debug mode (print extra data)')

    args = argp.parse_args()

    # Check parameters
    if args.capacity not in CAPACITY_METRIC.keys():
        argp.error('Capacity not valid')

    if args.period < 60 or args.period % 60 != 0:
        argp.error('Period must be at least 60 seconds and multiple of 60.')

    if args.capacity in ['read_index', 'write_index']:
        if not args.index:
            argp.error('If capacity is read_index or write_index, an index'
                       ' name needs to be specified.')

    if ':' in args.warning and ':' in args.critical:
        try:
            values = args.warning.replace('%', '').split(':') + \
                args.critical.replace('%', '').split(':')
            [int(x) for x in values]

        except ValueError:
            argp.error('Warning and Critical parameters need to be numbers'
                       ' representing a percentage or a fixed value.')
    else:
        argp.error('Warning and Critical parameters should be two values '
                   'separated by the colon character: \':\'')

    # Get data from Cloudwatch
    end_time = datetime.datetime.utcnow()
    start_time = end_time - datetime.timedelta(minutes=args.timedelta)

    cw = boto.ec2.cloudwatch.connect_to_region(args.region)
    cw_dimensions = {'TableName': [args.table]}
    if args.capacity in ['read_index', 'write_index']:
        cw_dimensions['GlobalSecondaryIndexName'] = [args.index]
    result_provisioned = cw.get_metric_statistics(period=args.period,
                                                  start_time=start_time,
                                                  end_time=end_time,
                                                  metric_name=CAPACITY_METRIC[
                                                      args.capacity][
                                                          'provisioned'],
                                                  namespace='AWS/DynamoDB',
                                                  statistics=['Sum'],
                                                  dimensions=cw_dimensions,
                                                  unit='Count',
                                                  )

    result_consumed = cw.get_metric_statistics(period=args.period,
                                               start_time=start_time,
                                               end_time=end_time,
                                               metric_name=CAPACITY_METRIC[
                                                   args.capacity]['consumed'],
                                               namespace='AWS/DynamoDB',
                                               statistics=['Sum'],
                                               dimensions=cw_dimensions,
                                               unit='Count',
                                               )

    if len(result_provisioned) == 0:
        status = 'UNKNOWN'
        print(status + ': Could not get table capacities. Is the table name '
              'correct?')
        sys.exit(NAGIOS_STATUSES[status])

    values_provisioned = []
    for n in result_provisioned:
        values_provisioned.append({'provisioned': n['Sum'],
                                   'date': n['Timestamp']})
    df_provisioned = pd.DataFrame(values_provisioned).set_index('date')

    values_consumed = []
    for n in result_consumed:
        values_consumed.append({'consumed': n['Sum']/args.period,
                                'date': n['Timestamp']})
    if len(result_consumed) == 0:
        values_consumed.append({'consumed': 0,
                                'date': df_provisioned.head(1).index[0]})
        values_consumed.append({'consumed': 0,
                                'date': df_provisioned.tail(1).index[0]})
    df_consumed = pd.DataFrame(values_consumed).set_index('date')

    df = pd.concat([df_consumed, df_provisioned], axis=1, join='outer')

    first_date = df.sort_index(0).index[0]
    df = df.reindex(pd.date_range(first_date,
                                  periods=args.timedelta/(args.period/60),
                                  freq=pd.DateOffset(
                                      minutes=args.period/60))).interpolate(
                                          limit=args.timedelta/(
                                              args.period/60),
                                          limit_direction='both')

    if args.debug:
        print("Data collected:")
        print(df)

    # set default output
    msg = ''
    status = 'OK'
    datapoints_exceeded = 0
    total_datapoints = len(df)

    # Warning
    warning_0 = int(args.warning.replace('%', '').split(':')[0])
    warning_1 = int(args.warning.replace('%', '').split(':')[1])
    if '%' in args.warning.split(':')[0]:
        # first argument value is percentage
        len_w = ((100 - (df.provisioned - df.consumed) / df.provisioned * 100)
                 > warning_0).value_counts().get(True, 0)
    else:
        # first argument value is fixed value
        len_w = (df.provisioned - df.consumed
                 > warning_0).value_counts().get(True, 0)

    if '%' in args.warning.split(':')[1]:
        # second argument value is percentage
        if (float(len_w) / float(total_datapoints) * 100) > warning_1:
            status = 'WARNING'
            datapoints_exceeded = len_w
            threshold = args.warning.split(':')[0]
    else:
        # second argument value is fixed value
        if len_w > warning_1:
            status = 'WARNING'
            datapoints_exceeded = len_w
            threshold = args.warning.split(':')[0]

    if status == 'OK':
        msg = 'Table ' + args.table + ' ' + args.capacity + ' capacity is ' + \
              'under the specified thresholds'
    else:
        msg = 'Table ' + args.table + ' ' + args.capacity + ' capacity ' + \
              'has exceeded the threshold of ' + \
              threshold + ' for a sum of ' + str(datapoints_exceeded) + \
              ' datapoints from a total of ' + str(total_datapoints)

    # Critical
    critical_0 = int(args.critical.replace('%', '').split(':')[0])
    critical_1 = int(args.critical.replace('%', '').split(':')[1])
    if '%' in args.critical.split(':')[0]:
        # first argument value is percentage
        len_c = ((100 - (df.provisioned - df.consumed) / df.provisioned * 100)
                 > critical_0).value_counts().get(True, 0)
    else:
        # first argument value is fixed value
        len_c = (df.provisioned - df.consumed
                 > critical_0).value_counts().get(True, 0)

    if '%' in args.critical.split(':')[1]:
        # second argument value is percentage
        if (float(len_w) / float(total_datapoints) * 100) > critical_1:
            status = 'CRITICAL'
            datapoints_exceeded = len_c
            threshold = args.critical.split(':')[0]
    else:
        # second argument value is fixed value
        if len_c > critical_1:
            status = 'CRITICAL'
            datapoints_exceeded = len_c
            threshold = args.critical.split(':')[0]

    if status == 'OK':
        msg = 'Table ' + args.table + ' ' + args.capacity + ' capacity is ' + \
              'under the specified thresholds'
    else:
        msg = 'Table ' + args.table + ' ' + args.capacity + ' capacity ' + \
              'has exceeded the threshold of ' + \
              threshold + ' for a sum of ' + str(datapoints_exceeded) + \
              ' datapoints from a total of ' + str(total_datapoints)

    print(status + ': ' + msg)
    sys.exit(NAGIOS_STATUSES[status])

if __name__ == "__main__":
    main()
