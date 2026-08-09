from django.db import migrations


def spalte_entfernen(apps, schema_editor):
    """Entfernt eine verwaiste Datenbank-Spalte (admin_menu_verstecken auf Profil), die aus
    einer laengst zurueckgenommenen Aenderung (Commit bba598e, revertet in 84d7c1d) stammt.
    Der Feld existiert seitdem in keinem Modell/keiner Migration mehr, blieb aber auf manchen
    Datenbanken (z.B. Produktion) als NOT-NULL-Spalte zurueck und liess dort das Anlegen neuer
    Profil-Zeilen (z.B. beim ersten Aufruf von 'Mein Konto') mit einem IntegrityError scheitern."""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("PRAGMA table_info(mitglieder_profil)")
        spalten = [row[1] for row in cursor.fetchall()]
        if "admin_menu_verstecken" in spalten:
            cursor.execute("ALTER TABLE mitglieder_profil DROP COLUMN admin_menu_verstecken")


def spalte_wiederherstellen(apps, schema_editor):
    # Absichtlich kein Zurueckholen der verwaisten Spalte - sie gehoerte nie zum Modell.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("mitglieder", "0046_gruppe_delete_einstellungen_remove_termin_gruppe_and_more"),
    ]

    operations = [
        migrations.RunPython(spalte_entfernen, spalte_wiederherstellen),
    ]
