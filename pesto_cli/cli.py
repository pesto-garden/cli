import collections.abc
import json
import os
import re

import click
import jinja2
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


def recursive_get(d, path, separator="."):
    keys = path.split(separator)
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

    if filter and not all((match(document, f) for f in filter)):
        return False
    if exclude and any((match(document, f) for f in exclude)):
        return False
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
    documents = json.loads(input.read())
    new_documents = [d for d in documents if keep_document(d, filter, exclude)]

    click.echo(json.dumps(new_documents, indent=2))
    click.echo(f"{len(new_documents)} matching documents", err=True)


TAG_REGEX = r'((#|\+{1,5}|-{1,5}|~|\?|!|@)([:A-zÀ-ÿ\d][:A-zÀ-ÿ\d-]*(=(true|false|[:A-zÀ-ÿ\d-]+|"[^"]*")?(-?\d*(\.(\d+))?)?)?))'


def flatten(d, parent_key="", sep="_", replace=":.- "):
    items = []
    for k, v in d.items():
        new_key = parent_key + sep + k if parent_key else k
        if isinstance(v, collections.abc.MutableMapping):
            items.extend(flatten(v, new_key, sep=sep).items())
        else:
            for char in replace:
                new_key = new_key.replace(char, sep)
            items.append((new_key, v))
    return dict(items)


def remove_annotations(text):
    matches = re.findall(TAG_REGEX, text)
    for match in matches:
        if match[0].startswith("@"):
            text = text.replace(match[0], "")
    return text


def write_file(filename, content, output_dir, replace=False):
    path = os.path.join(output_dir, filename)
    if os.path.exists(path) and not replace:
        raise ValueError("{} already exists".format(path))

    with open(path, "w") as f:
        f.write(content)


MARKDOWN_TEMPLATE = os.path.join(os.path.dirname(__file__), "markdown.jinja2")


@cli.command("build-markdown")
@click.argument("input", type=click.File("r"))
@click.argument(
    "output_dir", type=click.Path(dir_okay=True, file_okay=False, exists=True)
)
@click.option("--file-name", type=str, default="{created_at}.md")
@click.option(
    "--template",
    type=click.Path(file_okay=True, exists=True, dir_okay=False),
    default=MARKDOWN_TEMPLATE,
)
@click.option("--annotations/--no-annotations", default=False)
@click.option("--front-matter/--no-front-matter", default=True)
@click.option("--dry-run/--no-dry-run", default=False)
@click.option("--force/--no-force", default=False)
@click.option("--front-matter-fields", type=str, help="title,date,layout,category")
@click.option(
    "--aliases", "-a", type=str, default=[], multiple=True, help="date=created_at"
)
@click.option(
    "--defaults",
    "-d",
    type=str,
    default=[],
    multiple=True,
    help="layout=something.html",
)
@click.option(
    "--overrides", "-o", type=str, default=[], multiple=True, help="category=Posts"
)
def build_markdown(
    input,
    output_dir,
    template,
    file_name,
    annotations,
    dry_run,
    force,
    front_matter,
    defaults,
    aliases,
    overrides,
    front_matter_fields,
):
    """
    Build markdown posts from a database dump
    """
    documents = json.loads(input.read())

    click.echo(f"Building {len(documents)} documents", err=True)
    for document in documents:

        context = {key: value or "" for key, value in flatten(document).items()}
        for alias in aliases:
            key, value = alias.split("=")
            if value in context:
                context[key] = context[value]
        for default in defaults:
            key, value = default.split("=")

            try:
                v = json.loads(value)
            except json.decoder.JSONDecodeError:
                v = value
            context.setdefault(key, v)
        for override in overrides:
            key, value = override.split("=")
            try:
                v = json.loads(value)
            except json.decoder.JSONDecodeError:
                v = value
            context[key] = v
        if front_matter and front_matter_fields:
            context["front_matter"] = {}
            for field in front_matter_fields.split(","):
                field = field.strip()
                if field in context:
                    context["front_matter"][field] = context[field]

        with open(template) as f:
            content = f.read()
            j2_template = jinja2.Environment(loader=jinja2.BaseLoader).from_string(
                content
            )

        body = j2_template.render(**context)
        if not annotations:
            body = remove_annotations(body)

        filename = file_name.format(**context)
        click.echo(f"Writing {filename}…", err=True)
        if not dry_run:
            write_file(filename, body, output_dir, replace=force)


if __name__ == "__main__":
    cli()
