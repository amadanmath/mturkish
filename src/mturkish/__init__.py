#!/usr/bin/env python

import sys
import hashlib
import json
from datetime import datetime
from types import SimpleNamespace
from xml.dom.minidom import parseString

import click
import boto3
import jmespath



environments = {
    "live": SimpleNamespace(
        endpoint="https://mturk-requester.us-east-1.amazonaws.com",
        preview="https://www.mturk.com/mturk/preview",
        manage="https://requester.mturk.com/mturk/manageHITs",
    ),
    "sandbox": SimpleNamespace(
        endpoint="https://mturk-requester-sandbox.us-east-1.amazonaws.com",
        preview="https://workersandbox.mturk.com/mturk/preview",
        manage="https://requestersandbox.mturk.com/mturk/manageHITs",
    ),
}


def json_default(obj):
    import calendar, datetime

    if isinstance(obj, datetime.datetime):
        if obj.utcoffset() is not None:
            obj = obj - obj.utcoffset()
        millis = int(
            calendar.timegm(obj.timetuple()) * 1000 +
            obj.microsecond / 1000
        )
        return millis
    raise TypeError('Not sure how to serialize %s' % (obj,))


def echojson(data):
    click.echo(json.dumps(data, default=json_default))


operation_result_keys = {
    'list_hits': 'HITs',
    'list_assignments_for_hit': 'Assignments',
}
def get_all(obj, operation, limit=None, query=None, **kwargs):
    result_key = operation_result_keys[operation]
    paginator = obj.client.get_paginator(operation)
    config = {
        'MaxItems': obj.max_items,
        'PageSize': 25,
    }
    iterator = paginator.paginate(PaginationConfig=config, **kwargs)
    result = []
    for page in iterator:
        items = page[result_key]
        if query:
            items = jmespath.search(query, items)
        result.extend(items)
        if limit and len(result) >= limit:
            return result[:limit]
    return result


def get_assignment_ids(obj, hit_ids, include_approved=False):
    assignment_ids = []
    kinds = ['Submitted']
    if include_approved:
        kinds = ['Submitted', 'Approved']
    else:
        kinds = ['Submitted']
    for hit_id in hit_ids:
        assignments = get_all(
            obj,
            'list_assignments_for_hit',
            HITId=hit_id,
            AssignmentStatuses=kinds,
        )
        assignment_ids.extend(assignment["AssignmentId"] for assignment in assignments)
    return assignment_ids




@click.group(context_settings={"auto_envvar_prefix": "MTURKISH"})
@click.option('--profile', '-p', help='AWS profile name')
@click.option('--sandbox', '-s', is_flag=True, help='Use AMT sandbox')
@click.option('--max-items', '-m', type=int, default=1000, help='Max items to retrieve for any request')
@click.pass_context
def cli(ctx, profile, sandbox, max_items):
    environment = environments['sandbox' if sandbox else 'live']
    session = boto3.Session(profile_name=profile)
    client = session.client(
        service_name='mturk',
        region_name='us-east-1',
        endpoint_url=environment.endpoint,
    )
    ctx.obj = SimpleNamespace(
        client=client,
        max_items=max_items,
    )


@cli.command()
@click.argument('hit-type-id')
@click.argument('hit-layout-id')
@click.argument('filename', required=False)
@click.option('--annotation', '-a', help='requester annotation')
@click.option('--lifetime', '-t', type=int, default=3600, help='lifetime (seconds)')
@click.option('--num-assignments', '-n', type=int, default=1, help='maximum number of assignments')
@click.option('--ids', '-i', is_flag=True, help='only list IDs')
@click.pass_obj
def make_hits(obj, hit_type_id, hit_layout_id, filename, annotation, lifetime, num_assignments, ids):
    if filename is None:
        file = sys.stdin
    else:
        file = open(filename, 'rt')
    results = []
    with file:
        for row in file:
            params = [
                {
                    'Name': 'json',
                    'Value': json.dumps(json.loads(row)), # canonicalisation, sanity check
                }
            ]
            unique_token = hashlib.md5((hit_type_id + hit_layout_id + (annotation or '') + row).encode()).hexdigest()
            kwargs = {}
            if annotation:
                kwargs["RequesterAnnotation"] = annotation
            response = obj.client.create_hit_with_hit_type(
                HITTypeId=hit_type_id,
                HITLayoutId=hit_layout_id,
                HITLayoutParameters=params,
                UniqueRequestToken=unique_token,
                MaxAssignments=num_assignments,
                LifetimeInSeconds=lifetime,
                **kwargs,
            )
            result = response['HIT']
            if ids:
                result = result['HITId']
            else:
                del result['Questions']
            results.append(result)
        if ids:
            print('\n'.join(results))
        else:
            echojson(results)


@cli.command()
@click.argument('hit-ids', nargs=-1)
@click.pass_obj
def expire_hits(obj, hit_ids):
    epoch = datetime.utcfromtimestamp(0)
    results = []
    for hit_id in hit_ids:
        response = obj.client.update_expiration_for_hit(
            HITId=hit_id,
            ExpireAt=epoch,
        )
        results.append(response)
    echojson(results)


@cli.command()
@click.argument('hit-ids', nargs=-1)
@click.pass_obj
def delete_hits(obj, hit_ids):
    results = []
    for hit_id in hit_ids:
        response = obj.client.delete_hit(
            HITId=hit_id,
        )
        results.append(response)
    echojson(results)


@cli.command()
@click.option('--limit', '-l', type=int, default=10, help='limit')
@click.option('--query', '-q', help='JMESPath query')
@click.option('--annotation', '-a', help='filter by annotation')
@click.option('--ids', '-i', is_flag=True, help='only list IDs')
@click.pass_obj
def list_hits(obj, limit, query, annotation, ids):
    if annotation:
        annotation_json = json.dumps(annotation).replace('`', r'\`')
        ann_query = f'[?contains(RequesterAnnotation || ``, `{annotation_json}`)]'
        if query:
            query = f'{ann_query} | {query}'
        else:
            query = ann_query
    hits = get_all(
        obj,
        'list_hits',
        limit=limit,
        query=query,
    )
    for hit in hits:
        del hit['Question']
        del hit['QualificationRequirements']
    if ids:
        hit_ids = (hit["HITId"] for hit in hits)
        click.echo('\n'.join(hit_ids))
    else:
        echojson(hits)


@cli.command()
@click.argument('hit-id')
@click.pass_obj
def get_hit(obj, hit_id):
    response = obj.client.get_hit(
        HITId=hit_id,
    )
    hit = response.pop('HIT')
    del hit["Question"]
    echojson(hit)


@cli.command()
@click.argument('hit-ids', nargs=-1)
@click.option('--limit', '-l', default=10, help='limit')
@click.option('--query', '-q', help='JMESPath query')
@click.option('--ids', '-i', is_flag=True, help='only list IDs')
@click.pass_obj
def list_assignments(obj, hit_ids, limit, query, ids):
    results = []
    for hit_id in hit_ids:
        assignments = get_all(
            obj,
            'list_assignments_for_hit',
            limit=limit,
            query=query,
            HITId=hit_id,
            AssignmentStatuses=['Approved', 'Submitted'],
        )
        for assignment in assignments:
            doc = parseString(assignment["Answer"])
            data = {}
            for answer in doc.getElementsByTagName('Answer'):
                key = " ".join(t.nodeValue for t in answer.getElementsByTagName('QuestionIdentifier')[0].childNodes if t.nodeType == t.TEXT_NODE)
                value = " ".join(t.nodeValue for t in answer.getElementsByTagName('FreeText')[0].childNodes if t.nodeType == t.TEXT_NODE)
                data[key] = value
            assignment["Answer"] = data
        results.extend(assignments)
        if limit and len(results) > limit:
            results = results[:limit]
            break
    if ids:
        result_ids = (result["AssignmentId"] for result in results)
        click.echo('\n'.join(result_ids))
    else:
        echojson(results)


@cli.command()
@click.argument('assignment-ids', nargs=-1)
@click.option('--message', '-m', help='requester feedback')
@click.option('--all', '-a', 'all_of_hits', is_flag=True, help='apply to all assignments of given hits instead')
@click.option('--force', '-f', is_flag=True, help='approve even rejected hits')
@click.pass_obj
def approve(obj, assignment_ids, message, all_of_hits):
    if all_of_hits:
        hit_ids = assignment_ids
        assignment_ids = get_assignment_ids(obj, hit_ids, force)
    result = []
    for assignment_id in assignment_ids:
        kwargs = {
            'OverrideRejection': force,
        }
        if message:
            kwargs["RequesterFeedback"] = message
        response = obj.client.approve_assignment(
            AssignmentId=assignment_id,
            **kwargs,
        )
        result.append(response)
    echojson(result)


@cli.command()
@click.argument('assignment-ids', nargs=-1)
@click.option('--message', '-m', required=True, help='requester feedback')
@click.option('--all', '-a', 'all_of_hits', is_flag=True, help='apply to all assignments of given hits instead')
@click.pass_obj
def reject(obj, assignment_ids, message, all_of_hits):
    if all_of_hits:
        hit_ids = assignment_ids
        assignment_ids = get_assignment_ids(obj, hit_ids)
    result = []
    for assignment_id in assignment_ids:
        kwargs = {}
        if message:
            kwargs["RequesterFeedback"] = message
        response = obj.client.reject_assignment(
            AssignmentId=assignment_id,
            **kwargs,
        )
        result.append(response)
    echojson(result)





if __name__ == '__main__':
    cli(auto_envvar_prefix='MTURKISH')
