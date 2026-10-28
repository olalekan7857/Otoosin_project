from django.db import migrations


TOP_LEVEL = [
    ("Meats", "meats", "meat_group", 1),
    ("Fish", "fish", "seafood", 2),
    ("Live Animals", "live-animals", "live_animal", 3),
    ("Eggs", "eggs", "eggs", 4),
    ("Veggies", "veggies", "vegetables", 5),
    ("Fruits", "fruits", "fruits", 6),
]

MEAT_CHILDREN = [
    ("Pork", "pork", "red_meat", 1),
    ("Chicken", "chicken", "poultry", 2),
    ("Turkey", "turkey", "poultry", 3),
    ("Beef", "beef", "red_meat", 4),
    ("Goat Meat", "goat-meat", "red_meat", 5),
]


def seed_categories(apps, schema_editor):
    Category = apps.get_model("Otoosin", "Category")
    categories = {}

    for name, slug, kind, sort_order in TOP_LEVEL:
        category, _ = Category.objects.get_or_create(
            slug=slug,
            defaults={
                "name": name,
                "kind": kind,
                "sort_order": sort_order,
                "is_active": True,
            },
        )
        categories[slug] = category

    meats = categories["meats"]
    for name, slug, kind, sort_order in MEAT_CHILDREN:
        Category.objects.get_or_create(
            slug=slug,
            defaults={
                "name": name,
                "kind": kind,
                "sort_order": sort_order,
                "is_active": True,
                "parent": meats,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("Otoosin", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_categories, migrations.RunPython.noop),
    ]
