
```bash
python3 -m venv venv/
pip install .

PESTO_ACCESS_KEY=xxx
venv/bin/pestoctl download DEFAULT > data.json

# settings
venv/bin/pestoctl filter data.json -f type=setting

# collections
venv/bin/pestoctl filter data.json -f type=collection

# documents where text contains a keyword
venv/bin/pestoctl filter data.json -f "fragments.text.content__in=hello"

# documents where form data matches a value
venv/bin/pestoctl filter data.json -f "fragments.form.data.animal=Cat"

# documents with a tag
venv/bin/pestoctl filter data.json -f tags__in=sleep

# documents between two dates
venv/bin/pestoctl filter data.json -f "created_at>=2021-01-12" -f "created_at<=2022-01-01"
```