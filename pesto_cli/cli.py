import json

import click
import requests

access_key_option = click.option(
    "--access-key",
    envvar="PESTO_ACCESS_KEY",
    required=True,
    help="An access key to authenticate to the API.",
)
server_url_option = click.option(
    "-s",
    "--server-url",
    envvar="PESTO_SERVER_URL",
    default="https://db.pesto.garden/",
    required=True,
    help="URL of the Pesto server.",
)


@click.group()
def cli():
    pass


@cli.command()
@click.argument("database")
@access_key_option
@server_url_option
@click.option(
    "--parse-content/--no-parse-content",
    default=True,
    help="Try to parse the content of the content field as JSON.",
)
def download(database, parse_content, server_url, access_key):
    "Download a full dump of given database in JSON format."
    url = f"{server_url}sync/db/{database}/documents"
    response = requests.get(url, headers={"Authorization": f"Bearer {access_key}"})
    response.raise_for_status()

    data = response.json()
    if parse_content:
        new_data = []
        for document in data:
            document.update(json.loads(document["content"]))
            del document["content"]
            new_data.append(document)
        data = new_data
    click.echo(json.dumps(data, indent=2))
    click.echo(f"{len(data)} documents found", err=True)


def recursive_get(d, path):
    keys = path.split(".")
    v = d
    for key in keys:
        v = v[key]
    return v


def autocast(v1, v2):
    if isinstance(v1, str):
        return str(v2)
    if isinstance(v1, list):
        return str(v2)
    if isinstance(v1, bool):
        correspondances = {
            "true": True,
            "yes": True,
            "1": True,
            "false": False,
            "no": False,
            "0": False,
        }
        return correspondances[str(v2).lower()]

    return v2


def match_lookup(value, lookup, lookup_value):
    lookup_value = autocast(value, lookup_value)

    if lookup == "iexact":
        return lookup_value.lower() == value.lower()
    if lookup == "exact":
        return lookup_value == value
    if lookup == "ne":
        return lookup_value != value
    if lookup == "gt":
        import pdb

        pdb.set_trace()

        return value > lookup_value
    if lookup == "gte":
        print("HELLO", value, lookup_value)
        return value >= lookup_value
    if lookup == "lt":
        return value < lookup_value
    if lookup == "lte":
        return value <= lookup_value
    if lookup == "in":
        return lookup_value in value
    if lookup == "exists":
        return True

    return False


def match(document, f):
    try:
        if ">=" in f:
            key, lookup_value = f.split(">=")
            lookup = "gte"
        elif "!=" in f:
            key, lookup_value = f.split("!=")
            lookup = "ne"
        elif "<=" in f:
            key, lookup_value = f.split("<=")
            lookup = "lte"
        elif "<" in f:
            key, lookup_value = f.split("<")
            lookup = "lt"
        elif ">" in f:
            key, lookup_value = f.split(">")
            lookup = "gt"
        elif "=" in f:
            key, lookup_value = f.split("=")
            lookup = "exact"
        else:
            # we check only for the presence of a non empty field
            key = f
            lookup = "exists"
            lookup_value = None
        if "__" in key:
            key, lookup = key.split("__")
        value = recursive_get(document, key)
        if match_lookup(value, lookup, lookup_value):
            return True
    except KeyError:
        return False


def keep_document(document, filter, exclude):
    if filter:
        return all((match(document, f) for f in filter))
    if exclude:
        return not any((match(document, f) for f in exclude))
    return True


@cli.command("filter")
@click.argument("input", type=click.File("r"))
@click.option(
    "-f", "--filter", help="Filter entries using the given field/value", multiple=True
)
@click.option(
    "-e",
    "--exclude",
    help="Exclude entries matching the given field/value",
    multiple=True,
)
def filter_(input, filter, exclude):
    """
    Filter/exclude documents from a database dump, outputting the result.
    """
    data = json.loads(input.read())
    new_data = [d for d in data if keep_document(d, filter, exclude)]

    click.echo(json.dumps(new_data, indent=2))
    click.echo(f"{len(new_data)} matching documents", err=True)


if __name__ == "__main__":
    cli()
