KONTAKTE_ABTEILUNGEN = [
    {
        "abteilung": "Basketball",
        "gruppen": [
            {"gruppe": "", "trainer": "Mark Christel", "telefon": "0176 87641072", "email": "Mark.Christel@djk-oberasbach.de"},
        ],
    },
    {
        "abteilung": "Fitnessboxen",
        "gruppen": [
            {"gruppe": "", "trainer": "Maxi Göppert", "telefon": "", "email": "Maxi.Goeppert@djk-oberasbach.de"},
        ],
    },
    {
        "abteilung": "Fußball",
        "gruppen": [
            {"gruppe": "1. Herren", "trainer": "Tobias Hösch", "telefon": "", "email": "info@djk-oberasbach.de"},
            {"gruppe": "2. Herren", "trainer": "Aniello Rahm, Kevin Neubing", "telefon": "", "email": "info@djk-oberasbach.de"},
            {"gruppe": "alt Herren", "trainer": "Achim Lengl, Daniel Kirchdorfer", "telefon": "", "email": "info@djk-oberasbach.de"},
            {"gruppe": "E Jugend", "trainer": "Robert Klingl", "telefon": "", "email": "Jugendfussball@djk-oberasbach.de"},
            {"gruppe": "F1", "trainer": "Marcel Dietrich", "telefon": "", "email": "Jugendfussball@djk-oberasbach.de"},
            {"gruppe": "F2", "trainer": "Achim Lengl", "telefon": "", "email": "Jugendfussball@djk-oberasbach.de"},
            {"gruppe": "G1", "trainer": "Franz Feßmann", "telefon": "", "email": "Jugendfussball@djk-oberasbach.de"},
            {"gruppe": "G2", "trainer": "Cristian Krenzer", "telefon": "", "email": "Christian.Krenzer@djk-oberasbach.de"},
            {"gruppe": "Ballschule", "trainer": "Christin Friedrich", "telefon": "", "email": "Jugendfussball@djk-oberasbach.de"},
            {"gruppe": "Walking Football", "trainer": "", "telefon": "", "email": "info@djk-oberasbach.de"},
        ],
    },
    {
        "abteilung": "Skigymnastik",
        "gruppen": [
            {"gruppe": "", "trainer": "Sepp und Otto", "telefon": "0911 692863", "email": ""},
        ],
    },
    {
        "abteilung": "Karnevalistischer Tanzsport",
        "gruppen": [
            {"gruppe": "Weiße Garde", "trainer": "Emilia Castaneda, Angie Sabo", "telefon": "", "email": "Angie.Sabo@djk-oberasbach.de"},
            {"gruppe": "Rote Garde", "trainer": "Emilia Castaneda, Angie Sabo", "telefon": "", "email": "Angie.Sabo@djk-oberasbach.de"},
            {"gruppe": "Solistinnen", "trainer": "Anastasija Riedlinger", "telefon": "", "email": "Anastasija.Riedlinger@djk-oberasbach.de"},
        ],
    },
    {
        "abteilung": "Kinderturnen",
        "gruppen": [
            {"gruppe": "", "trainer": "Brinny Wigner", "telefon": "", "email": "info@djk-oberasbach.de"},
        ],
    },
    {
        "abteilung": "ZUMBA",
        "gruppen": [
            {"gruppe": "", "trainer": "Barbara", "telefon": "0172 8600711", "email": "Zumba@djk-oberasbach.de"},
        ],
    },
]


def kontakte_abteilungen(request):
    return {
        "kontakte_abteilungen": sorted(KONTAKTE_ABTEILUNGEN, key=lambda eintrag: eintrag["abteilung"].lower())
    }


def ungelesene_nachrichten(request):
    if not request.user.is_authenticated:
        return {"ungelesene_nachrichten_anzahl": 0}
    from .models import Nachricht

    anzahl = Nachricht.objects.filter(empfaenger=request.user, gelesen=False).count()
    return {"ungelesene_nachrichten_anzahl": anzahl}


def offene_aufgaben(request):
    if not request.user.is_authenticated:
        return {"offene_aufgaben_anzahl": 0}
    from .models import Aufgabe

    anzahl = Aufgabe.objects.filter(zugewiesen_an=request.user, erledigt=False).count()
    return {"offene_aufgaben_anzahl": anzahl}
