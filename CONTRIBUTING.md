# Contributing to workflow-verify

Thanks for your interest in contributing! This guide covers the most common ways to help.

## Development Setup

```bash
git clone https://github.com/your-org/workflow-verify.git
cd workflow-verify
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest tests/ -v
```

## Linting & Type Checking

```bash
ruff check src/ tests/
ruff format src/ tests/
mypy src/workflow_verify/ --ignore-missing-imports
```

## Adding a Schema to the Registry

This is the easiest way to contribute. Schemas live in `src/workflow_verify/registry/schemas/` organized by category:

```
schemas/
├── common/          # Reusable building blocks (Person, Address, Money)
├── communication/   # Messaging schemas (Slack, Email, Webhook)
├── crm/             # CRM objects (Salesforce, HubSpot, CRMZero)
├── data/            # Data infrastructure (Postgres, Stripe, CSV)
└── enrichment/      # Data enrichment (Clearbit, Clay, Apollo)
```

### Schema YAML Format

Create a YAML file in the appropriate category directory:

```yaml
# schemas/crm/my_crm_contact.yaml
name: MyCRMContact
description: Contact record from MyCRM
source: mycrm
fields:
  - name: id
    type: Text
    description: Unique contact ID
  - name: email
    type: Email
    description: Primary email address
  - name: first_name
    type: Text
    description: First name
  - name: last_name
    type: Text
    description: Last name
  - name: created_at
    type: DateTime
    description: Creation timestamp
```

### Field Types

Use these type values:

| Type | Description |
|------|-------------|
| `Text` | Generic string |
| `Email` | Email address (subtype of Text) |
| `Url` | URL (subtype of Text) |
| `Phone` | Phone number (subtype of Text) |
| `Int` | Integer (subtype of Float) |
| `Float` | Floating-point number |
| `Bool` | Boolean |
| `Date` | Date |
| `DateTime` | Date with time |
| `Json` | Arbitrary JSON |
| `Any` | Any type (escape hatch) |

### Validation Expressions

Fields can include optional validation:

```yaml
  - name: score
    type: Int
    description: Lead score
    validate: "0 <= value <= 100"
```

### Testing Your Schema

```bash
# Verify it loads
python -c "from workflow_verify import load_schema; s = load_schema('crm/my_crm_contact'); print(f'{s.name}: {len(s.fields)} fields')"

# Run the registry tests
pytest tests/test_registry.py -v

# Search for it
python -c "from workflow_verify import search_schemas; print([s.name for s in search_schemas('mycrm')])"
```

### Checklist

- [ ] YAML file in the correct category directory
- [ ] `name`, `description`, `source`, and `fields` are all present
- [ ] Field types use valid `WFType` values
- [ ] `pytest tests/test_registry.py` passes
- [ ] Schema loads without errors

## Adding a Dynamic Resolver

Dynamic resolvers fetch live schemas from service APIs. They live in `src/workflow_verify/resolvers/`. See `hubspot.py` or `stripe.py` for reference implementations.

A resolver must:

1. Subclass `SchemaResolver` from `resolvers/base.py`
2. Set `service_name`, `supported_objects`, and `env_var_names`
3. Implement `async def resolve(self, object_type, credentials, include_custom) -> Schema`
4. Be registered in `resolvers/__init__.py`

## Pull Request Guidelines

- Keep PRs focused on a single change
- Include tests for new functionality
- Run the full test suite before submitting
- Follow existing code style (enforced by ruff)

## Questions?

Open an issue on GitHub.
