"""Build the Wiener Philharmoniker Program Ranking from Concerts_in_Japan data.

Computes per-conductor performance counts for each work that appears 2+
times across all documented Japan tours, sorts by descending total, and
writes the table body into Program_Ranking.html.
"""
import re
import sys

REPO = "Wiener Philharmoniker"
CONCERTS = f"{REPO}/Concerts_in_Japan.html"
RANKING = f"{REPO}/Program_Ranking.html"

PLACEHOLDER_TOKENS = (
    "to be researched",
    "not documented",
)


def strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s)


def is_placeholder(w: str) -> bool:
    if not w or len(w) < 3:
        return True
    low = w.lower()
    if any(tok in low for tok in PLACEHOLDER_TOKENS):
        return True
    if low.startswith("various programs"):
        return True
    if low.startswith("program details") or low.startswith("program not"):
        return True
    if low.startswith("three concerts") or low.startswith("three programs"):
        return True
    if low.startswith("brahms symphonies and"):
        return True
    if low.startswith("german/austrian core"):
        return True
    # "J. Strauss: dance selections" / "Josef Strauss: dance selections" —
    # encore grab-bags from gala concerts, not a single named work.
    if low.endswith(": dance selections"):
        return True
    return False


CANONICAL = {
    # Symphony spelling canonicalisation
    "Beethoven: Sinfonie Nr. 1": "Beethoven: Sinfonie Nr. 1 C-Dur",
    "Beethoven: Sinfonie Nr. 2": "Beethoven: Sinfonie Nr. 2 D-Dur",
    "Beethoven: Sinfonie Nr. 4": "Beethoven: Sinfonie Nr. 4 B-Dur",
    "Beethoven: Sinfonie Nr. 5": "Beethoven: Sinfonie Nr. 5 c-Moll",
    "Beethoven: Sinfonie Nr. 7": "Beethoven: Sinfonie Nr. 7 A-Dur",
    "Beethoven: Sinfonie Nr. 8": "Beethoven: Sinfonie Nr. 8 F-Dur",
    "Brahms: Sinfonie Nr. 1": "Brahms: Sinfonie Nr. 1 c-Moll",
    "Brahms: Sinfonie Nr. 2": "Brahms: Sinfonie Nr. 2 D-Dur",
    "Brahms: Sinfonie Nr. 3": "Brahms: Sinfonie Nr. 3 F-Dur",
    "Brahms: Sinfonie Nr. 4": "Brahms: Sinfonie Nr. 4 e-Moll",
    # Symphonies with universally-known nicknames
    "Beethoven: Sinfonie Nr. 3":                       "Beethoven: Sinfonie Nr. 3 Es-Dur, <em>Eroica</em>",
    "Beethoven: Sinfonie Nr. 3 Es-Dur":                "Beethoven: Sinfonie Nr. 3 Es-Dur, <em>Eroica</em>",
    "Beethoven: Sinfonie Nr. 6":                       "Beethoven: Sinfonie Nr. 6 F-Dur, <em>Pastorale</em>",
    "Beethoven: Sinfonie Nr. 6 F-Dur":                 "Beethoven: Sinfonie Nr. 6 F-Dur, <em>Pastorale</em>",
    "Beethoven: Sinfonie Nr. 9":                       "Beethoven: Sinfonie Nr. 9 d-Moll, <em>Choral</em>",
    "Beethoven: Sinfonie Nr. 9 d-Moll":                "Beethoven: Sinfonie Nr. 9 d-Moll, <em>Choral</em>",
    "Schubert: Sinfonie Nr. 8":                        "Schubert: Sinfonie Nr. 8 h-Moll, <em>Unvollendete</em> D. 759",
    "Schubert: Sinfonie Nr. 8 h-Moll":                 "Schubert: Sinfonie Nr. 8 h-Moll, <em>Unvollendete</em> D. 759",
    "Schubert: Sinfonie Nr. 9":                        "Schubert: Sinfonie Nr. 9 C-Dur, <em>Die Große</em> D. 944",
    "Schubert: Sinfonie Nr. 9 C-Dur":                  "Schubert: Sinfonie Nr. 9 C-Dur, <em>Die Große</em> D. 944",
    "Tschaikowsky: Sinfonie Nr. 6":                    "Tschaikowsky: Sinfonie Nr. 6 h-Moll, <em>Pathétique</em>",
    "Tschaikowsky: Sinfonie Nr. 6 h-Moll":             "Tschaikowsky: Sinfonie Nr. 6 h-Moll, <em>Pathétique</em>",
    "Mozart: Sinfonie Nr. 35":                         "Mozart: Sinfonie Nr. 35 D-Dur, <em>Haffner</em>",
    "Mozart: Sinfonie Nr. 35 D-Dur":                   "Mozart: Sinfonie Nr. 35 D-Dur, <em>Haffner</em>",
    "Mozart: Sinfonie Nr. 38":                         "Mozart: Sinfonie Nr. 38 D-Dur, <em>Prager</em>",
    "Mozart: Sinfonie Nr. 38 D-Dur":                   "Mozart: Sinfonie Nr. 38 D-Dur, <em>Prager</em>",
    "Mozart: Sinfonie Nr. 41":                         "Mozart: Sinfonie Nr. 41 C-Dur, <em>Jupiter</em>",
    "Mozart: Sinfonie Nr. 41 C-Dur":                   "Mozart: Sinfonie Nr. 41 C-Dur, <em>Jupiter</em>",
    "Dvořák: Sinfonie Nr. 9":                          "Dvořák: Sinfonie Nr. 9 e-Moll, <em>Aus der Neuen Welt</em>",
    "Dvořák: Sinfonie Nr. 9 e-Moll":                   "Dvořák: Sinfonie Nr. 9 e-Moll, <em>Aus der Neuen Welt</em>",
    "Mendelssohn: Sinfonie Nr. 4":                     "Mendelssohn: Sinfonie Nr. 4 A-Dur, <em>Italienische</em>",
    "Mendelssohn: Sinfonie Nr. 4 A-Dur":               "Mendelssohn: Sinfonie Nr. 4 A-Dur, <em>Italienische</em>",
    "Bruckner: Sinfonie Nr. 4":                        "Bruckner: Sinfonie Nr. 4 Es-Dur, <em>Romantische</em>",
    "Bruckner: Sinfonie Nr. 4 Es-Dur":                 "Bruckner: Sinfonie Nr. 4 Es-Dur, <em>Romantische</em>",
    "Mozart: Sinfonie Nr. 36":                         "Mozart: Sinfonie Nr. 36 C-Dur, <em>Linzer</em>",
    "Mozart: Sinfonie Nr. 36 C-Dur":                   "Mozart: Sinfonie Nr. 36 C-Dur, <em>Linzer</em>",
    "Schubert: Sinfonie Nr. 4":                        "Schubert: Sinfonie Nr. 4 c-Moll, <em>Tragische</em>",
    "Schubert: Sinfonie Nr. 4 c-Moll":                 "Schubert: Sinfonie Nr. 4 c-Moll, <em>Tragische</em>",
    "Schubert: Sinfonie Nr. 6":                        "Schubert: Sinfonie Nr. 6 C-Dur, <em>Kleine</em>",
    "Schubert: Sinfonie Nr. 6 C-Dur":                  "Schubert: Sinfonie Nr. 6 C-Dur, <em>Kleine</em>",
    "Schumann: Sinfonie Nr. 3":                        "Schumann: Sinfonie Nr. 3 Es-Dur, <em>Rheinische</em>",
    "Schumann: Sinfonie Nr. 3 Es-Dur":                 "Schumann: Sinfonie Nr. 3 Es-Dur, <em>Rheinische</em>",
    "Prokofjew: Sinfonie Nr. 1":                       "Prokofjew: Sinfonie Nr. 1 D-Dur, <em>Klassische</em>",
    "Prokofjew: Sinfonie Nr. 1 D-Dur":                 "Prokofjew: Sinfonie Nr. 1 D-Dur, <em>Klassische</em>",
    "Haydn: Sinfonie Nr. 104":                         "Haydn: Sinfonie Nr. 104 D-Dur, <em>Londoner</em>",
    "Haydn: Sinfonie Nr. 104 D-Dur":                   "Haydn: Sinfonie Nr. 104 D-Dur, <em>Londoner</em>",
    "Haydn: Sinfonie Nr. 60":                          "Haydn: Sinfonie Nr. 60 C-Dur, <em>Il distratto</em>",
    "Haydn: Sinfonie Nr. 60 C-Dur":                    "Haydn: Sinfonie Nr. 60 C-Dur, <em>Il distratto</em>",
    "Mahler: Sinfonie Nr. 1":                          "Mahler: Sinfonie Nr. 1 D-Dur, <em>Titan</em>",
    "Mahler: Sinfonie Nr. 1 D-Dur":                    "Mahler: Sinfonie Nr. 1 D-Dur, <em>Titan</em>",
    # Brahms titled works
    "Brahms: Haydn-Variationen":                       "Brahms: <em>Variationen über ein Thema von Haydn</em>",
    "Brahms: Variationen über ein Thema von Haydn":    "Brahms: <em>Variationen über ein Thema von Haydn</em>",
    "Brahms: Tragische Ouvertüre":                     "Brahms: <em>Tragische Ouvertüre</em>",
    "Brahms: Akademische Festouvertüre":               "Brahms: <em>Akademische Festouvertüre</em>",
    # Beethoven overtures / dramatic music
    "Beethoven: Coriolan-Ouvertüre":                   "Beethoven: <em>Coriolan</em>-Ouvertüre",
    "Beethoven: Egmont":                               "Beethoven: <em>Egmont</em>",
    "Beethoven: Egmont-Ouvertüre":                     "Beethoven: <em>Egmont</em>-Ouvertüre",
    "Beethoven: Fidelio":                              "Beethoven: <em>Fidelio</em>",
    "Beethoven: Leonore-Ouvertüre Nr. 3":              "Beethoven: <em>Leonore</em>-Ouvertüre Nr. 3",
    "Beethoven: Ouvertüre Leonore Nr. 3":              "Beethoven: Ouvertüre <em>Leonore</em> Nr. 3",
    "Beethoven: Die Geschöpfe des Prometheus, Ouvertüre": "Beethoven: <em>Die Geschöpfe des Prometheus</em>, Ouvertüre",
    # R. Strauss tone poems / operas
    "R. Strauss: Till Eulenspiegel":                   "R. Strauss: <em>Till Eulenspiegels lustige Streiche</em>",
    "R. Strauss: Till Eulenspiegels lustige Streiche": "R. Strauss: <em>Till Eulenspiegels lustige Streiche</em>",
    "R. Strauss: Don Juan":                            "R. Strauss: <em>Don Juan</em>",
    "R. Strauss: Don Quixote":                         "R. Strauss: <em>Don Quixote</em>",
    "R. Strauss: Ein Heldenleben":                     "R. Strauss: <em>Ein Heldenleben</em>",
    "R. Strauss: Tod und Verklärung":                  "R. Strauss: <em>Tod und Verklärung</em>",
    "R. Strauss: Also sprach Zarathustra":             "R. Strauss: <em>Also sprach Zarathustra</em>",
    "R. Strauss: Eine Alpensinfonie":                  "R. Strauss: <em>Eine Alpensinfonie</em>",
    "R. Strauss: Der Rosenkavalier":                   "R. Strauss: <em>Der Rosenkavalier</em>",
    # Debussy
    "Debussy: La mer":                                 "Debussy: <em>La mer</em>",
    "Debussy: Prélude à l'après-midi d'un faune":      "Debussy: <em>Prélude à l'après-midi d'un faune</em>",
    "Debussy: Nocturnes":                              "Debussy: <em>Nocturnes</em>",
    "Debussy: aus Nocturnes":                          "Debussy: aus <em>Nocturnes</em>",
    # Stravinsky
    "Strawinsky: Le sacre du printemps":               "Strawinsky: <em>Le sacre du printemps</em>",
    "Strawinsky: Petruschka":                          "Strawinsky: <em>Petruschka</em>",
    "Strawinsky: L'oiseau de feu, Suite":              "Strawinsky: <em>L'oiseau de feu</em>, Suite",
    "Strawinsky: Suite aus L'oiseau de feu":           "Strawinsky: Suite aus <em>L'oiseau de feu</em>",
    "Strawinsky: Divertimento aus Le baiser de la fée": "Strawinsky: Divertimento aus <em>Le baiser de la fée</em>",
    # Wagner operas
    "Wagner: Tristan und Isolde":                      "Wagner: <em>Tristan und Isolde</em>",
    "Wagner: Tristan und Isolde, Vorspiel und Liebestod": "Wagner: <em>Tristan und Isolde</em>, Vorspiel und Liebestod",
    "Wagner: Tristan und Isolde, Liebestod":           "Wagner: <em>Tristan und Isolde</em>, Liebestod",
    "Wagner: Tannhäuser-Ouvertüre":                    "Wagner: <em>Tannhäuser</em>-Ouvertüre",
    "Wagner: Tannhäuser, Ouvertüre":                   "Wagner: <em>Tannhäuser</em>, Ouvertüre",
    "Wagner: Siegfried-Idyll":                         "Wagner: <em>Siegfried-Idyll</em>",
    "Wagner: Götterdämmerung, Orchesterstücke":        "Wagner: <em>Götterdämmerung</em>, Orchesterstücke",
    "Wagner: Die Meistersinger von Nürnberg, Vorspiel zum 1. Akt": "Wagner: <em>Die Meistersinger von Nürnberg</em>, Vorspiel zum 1. Akt",
    # Schubert overture
    "Schubert: Rosamunde-Ouvertüre":                   "Schubert: <em>Rosamunde</em>-Ouvertüre",
    # Mahler / Schumann
    "Mahler: Rückert-Lieder":                          "Mahler: <em>Rückert-Lieder</em>",
    "Schumann: Manfred-Ouvertüre":                     "Schumann: <em>Manfred</em>-Ouvertüre",
    # Ravel
    "Ravel: Daphnis et Chloé, Suite Nr. 2":            "Ravel: <em>Daphnis et Chloé</em>, Suite Nr. 2",
    "Ravel: La valse":                                 "Ravel: <em>La valse</em>",
    "Ravel: Boléro":                                   "Ravel: <em>Boléro</em>",
    "Ravel: Rhapsodie espagnole":                      "Ravel: <em>Rapsodie espagnole</em>",
    "Ravel: Rapsodie espagnole":                       "Ravel: <em>Rapsodie espagnole</em>",
    # Bartók / Hindemith
    "Bartók: Suite aus Der wunderbare Mandarin":       "Bartók: Suite aus <em>Der wunderbare Mandarin</em>",
    "Hindemith: Nobilissima visione, Suite":           "Hindemith: <em>Nobilissima visione</em>, Suite",
    "Hindemith: Sinfonie Mathis der Maler":            "Hindemith: Sinfonie <em>Mathis der Maler</em>",
    # Smetana / Mussorgsky / Respighi
    "Smetana: Die Moldau":                             "Smetana: <em>Die Moldau</em>",
    "Mussorgsky: Eine Nacht auf dem kahlen Berge":     "Mussorgsky: <em>Eine Nacht auf dem kahlen Berge</em>",
    "Mussorgsky: Bilder einer Ausstellung":            "Mussorgsky: <em>Bilder einer Ausstellung</em> (Bearbeitung von Maurice Ravel)",
    "Mussorgsky/Ravel: Bilder einer Ausstellung":      "Mussorgsky: <em>Bilder einer Ausstellung</em> (Bearbeitung von Maurice Ravel)",
    "Mussorgsky (arr. Schostakowitsch): Chowanschtschina, Vorspiel zum 1. Akt": "Mussorgsky (arr. Schostakowitsch): <em>Chowanschtschina</em>, Vorspiel zum 1. Akt",
    "Respighi: Pini di Roma":                          "Respighi: <em>Pini di Roma</em>",
    # Verdi / Rossini / Reznicek operas
    "Verdi: Requiem":                                  "Verdi: <em>Requiem</em>",
    "Verdi: I vespri siciliani, Ballettmusik Le quattro stagioni": "Verdi: <em>I vespri siciliani</em>, Ballettmusik <em>Le quattro stagioni</em>",
    "Verdi: Ouvertüre Giovanna d'Arco":                "Verdi: Ouvertüre <em>Giovanna d'Arco</em>",
    "Rossini: Il viaggio a Reims":                     "Rossini: <em>Il viaggio a Reims</em>",
    "Rossini: Ouvertüre Semiramide":                   "Rossini: Ouvertüre <em>Semiramide</em>",
    "Reznicek: Ouvertüre Donna Diana":                 "Reznicek: Ouvertüre <em>Donna Diana</em>",
    # Mozart operas / serenades
    "Mozart: Le nozze di Figaro, Ouvertüre":           "Mozart: <em>Le nozze di Figaro</em>, Ouvertüre",
    "Mozart: Ouvertüre Die Entführung aus dem Serail": "Mozart: Ouvertüre <em>Die Entführung aus dem Serail</em>",
    "Mozart: Serenade Nr. 13 G-Dur":                   "Mozart: Serenade Nr. 13 G-Dur, <em>Eine kleine Nachtmusik</em>",
    # Berg / Schönberg / Webern / Bach (arr.)
    "Berg: Wozzeck":                                   "Berg: <em>Wozzeck</em>",
    "Berg: Drei Orchesterstücke":                      "Berg: <em>Drei Orchesterstücke</em>",
    "Berg: Drei Stücke für Orchester":                 "Berg: <em>Drei Stücke für Orchester</em>",
    "Schönberg: Fünf Stücke für Orchester":            "Schönberg: <em>Fünf Stücke für Orchester</em>",
    "Webern: Fünf Stücke für Orchester":               "Webern: <em>Fünf Stücke für Orchester</em>",
    "Webern: Sechs Stücke für Orchester":              "Webern: <em>Sechs Stücke für Orchester</em>",
    "Webern: Passacaglia":                             "Webern: <em>Passacaglia</em>",
    "Bach (arr. Webern): Ricercar a 6 aus Das musikalische Opfer": "Bach (arr. Webern): Ricercar a 6 aus <em>Das musikalische Opfer</em>",
    # Wolf / Falla / Takemitsu / Sibelius
    "Wolf: Italienische Serenade":                     "Wolf: <em>Italienische Serenade</em>",
    "Falla: El sombrero de tres picos, Suite Nr. 2":   "Falla: <em>El sombrero de tres picos</em>, Suite Nr. 2",
    "Takemitsu: Nostalghia":                           "Takemitsu: <em>Nostalghia</em>",
    "Takemitsu: Visions":                              "Takemitsu: <em>Visions</em>",
    "Sibelius: Der Schwan von Tuonela":                "Sibelius: <em>Der Schwan von Tuonela</em>",
    # Rimsky-Korsakow
    "Rimsky-Korsakow: Scheherazade":                   "Rimsky-Korsakow: <em>Scheherazade</em>",
    "Rimsky-Korsakow: Russische Ostern, Ouvertüre":    "Rimsky-Korsakow: <em>Russische Ostern</em>, Ouvertüre",
    # Strauss family — dance music (entire title italic; genre suffix roman)
    "J. Strauss II: Annen-Polka":                      "J. Strauss II: <em>Annen-Polka</em>",
    "J. Strauss II: Kaiser-Walzer":                    "J. Strauss II: <em>Kaiser-Walzer</em>",
    "J. Strauss II: Wiener Blut, Walzer":              "J. Strauss II: <em>Wiener Blut</em>, Walzer",
    "J. Strauss II: Libellen-Polka mazur":             "J. Strauss II: <em>Libellen-Polka mazur</em>",
    "J. Strauss II: Perpetuum mobile":                 "J. Strauss II: <em>Perpetuum mobile</em>",
    "J. Strauss II: Pizzicato-Polka":                  "J. Strauss II: <em>Pizzicato-Polka</em>",
    "J. Strauss II: Egyptischer Marsch":               "J. Strauss II: <em>Egyptischer Marsch</em>",
    "J. Strauss II: Künstlerleben, Walzer":            "J. Strauss II: <em>Künstlerleben</em>, Walzer",
    "J. Strauss II: Ouvertüre Der Zigeunerbaron":      "J. Strauss II: Ouvertüre <em>Der Zigeunerbaron</em>",
    "J. Strauss II: Ouvertüre Die Fledermaus":         "J. Strauss II: Ouvertüre <em>Die Fledermaus</em>",
    "J. Strauss II: Ouvertüre Waldmeister":            "J. Strauss II: Ouvertüre <em>Waldmeister</em>",
    "Josef Strauss: Jockey-Polka":                                "Josef Strauss: <em>Jockey-Polka</em>",
    "Josef Strauss: Mein Lebenslauf ist Lieb' und Lust, Walzer":  "Josef Strauss: <em>Mein Lebenslauf ist Lieb' und Lust</em>, Walzer",
}


CAT_RE = re.compile(
    r"\b(op\.\s*\d+[a-z]?|KV\s*\d+[a-z]?|BWV\s*\d+|D\.\s*\d+|"
    r"Hob\.\s*[IV]+:\d+|WAB\s*\d+|Sz\.\s*\d+|TrV\s*\d+|HWV\s*\d+)\b"
)

KNOWN_COMPOSERS = (
    "Bach (arr. Webern)", "Bach", "Bartók", "Beethoven", "Berg", "Berlioz",
    "Bernstein", "Boulez", "Brahms", "Britten", "Bruckner", "Chopin",
    "Debussy", "Dukas", "Dvořák", "Falla", "Fortner", "Glinka", "Grieg",
    "Haydn", "Hindemith", "Honegger", "Janáček", "Liszt", "Magnus Lindberg",
    "Mahler", "Mendelssohn", "Mozart", "Mussorgsky (arr. Schostakowitsch)",
    "Mussorgsky/Ravel", "Mussorgsky", "Nielsen", "Prokofjew", "R. Strauss",
    "Rachmaninow", "Ravel", "Reger", "Respighi", "Reznicek", "Rimsky-Korsakow",
    "Rossini", "Saint-Saëns", "Schönberg", "Schostakowitsch", "Schubert",
    "Schumann", "Sibelius", "Smetana", "Strawinsky", "Takemitsu",
    "Tschaikowsky", "Unsuk Chin", "Verdi", "Wagner", "Weber", "Webern",
    "Wolf", "J. Strauss II", "J. Strauss", "Josef Strauss", "Adès", "Hayashi",
)

# Populated by main() from the concerts file.
CAT_MAP: dict = {}


def build_cat_map(concerts: str) -> dict:
    """Walk the concerts page → {(composer, work_base): catalogue_suffix}.
    Most common catalogue suffix wins per (composer, work_base)."""
    from collections import Counter
    tbody_m = re.search(r"<tbody>(.*?)</tbody>", concerts, re.DOTALL)
    if not tbody_m:
        return {}
    samples = {}
    for row in re.findall(r"<tr>.*?</tr>", tbody_m.group(1), re.DOTALL):
        tds = re.findall(r"<td>(.*?)</td>", row, re.DOTALL)
        if len(tds) < 6:
            continue
        composer = None
        for line in re.split(r"<br\s*/?>", tds[5]):
            plain = strip_tags(line).strip()
            if not plain:
                continue
            prefix = next((c for c in KNOWN_COMPOSERS if plain.startswith(c + ": ")), None)
            if prefix:
                composer = prefix
                work = plain[len(prefix) + 2:]
            else:
                work = plain
            if not composer:
                continue
            cat = CAT_RE.search(work)
            if not cat:
                continue
            base = work[:cat.start()].rstrip()
            base = re.sub(r",\s*[A-Za-zÉ][^,]*$", "", base).strip()
            base = re.sub(r"\s*\([^)]*\)\s*$", "", base).strip()
            samples.setdefault((composer, base), Counter())[cat.group(1)] += 1
    return {k: v.most_common(1)[0][0] for k, v in samples.items()}


def append_catalogue(display: str) -> str:
    """If display lacks a catalogue suffix but CAT_MAP has one, insert it
    BEFORE any trailing comma-style nickname so the order reads
    'WORK op. N, <em>Nickname</em>'."""
    plain = strip_tags(display)
    if CAT_RE.search(plain):
        return display
    composer = next((c for c in KNOWN_COMPOSERS if plain.startswith(c + ": ")), None)
    if not composer:
        return display
    base = plain[len(composer) + 2:]
    base = re.sub(r",\s*[A-Za-zÉ][^,]*$", "", base).strip()
    base = re.sub(r"\s*\([^)]*\)\s*$", "", base).strip()
    cat = CAT_MAP.get((composer, base))
    if not cat:
        return display
    nick_m = re.search(r",\s*<em>[^<]+</em>\s*$", display)
    if nick_m:
        return display[:nick_m.start()] + " " + cat + display[nick_m.start():]
    nick_m = re.search(r",\s*[A-ZÉ][^,]*$", display)
    if nick_m:
        return display[:nick_m.start()] + " " + cat + display[nick_m.start():]
    return display + " " + cat


def normalize_work(w: str) -> str:
    w = strip_tags(w).strip()
    # Strip catalog numbers
    w = re.sub(r"\s+op\.\s*\d+[a-z]?", "", w)
    w = re.sub(r"\s+KV\s*\d+[a-z]?", "", w)
    w = re.sub(r"\s+BWV\s*\d+", "", w)
    w = re.sub(r"\s+Sz\.\s*\d+", "", w)
    w = re.sub(r"\s+D\.\s*\d+", "", w)
    w = re.sub(r"\s+M\.\s*\d+", "", w)
    w = re.sub(r"\s+WWV\s*\d+", "", w)
    w = re.sub(r"\s+WAB\s*\d+", "", w)
    w = re.sub(r"\s+Hob\.\s*I:?\d+", "", w)
    w = re.sub(r"\s+HWV\s*\d+", "", w)
    w = re.sub(r"\s+TrV\s*\d+", "", w)
    # Strip trailing parentheticals repeatedly (nickname, format, conductor)
    prev = None
    while prev != w:
        prev = w
        w = re.sub(r"\s*\([^)]*\)\s*$", "", w).strip()
    if w in CANONICAL:
        return append_catalogue(CANONICAL[w])
    # Try once more with any trailing ", <Nickname>" comma-suffix removed —
    # so "Beethoven: Sinfonie Nr. 3 Es-Dur, Eroica" collapses to the same
    # CANONICAL row as "Beethoven: Sinfonie Nr. 3 Es-Dur".
    bare = re.sub(r",\s*[A-ZÉ][^,]*$", "", w).strip()
    if bare != w and bare in CANONICAL:
        return append_catalogue(CANONICAL[bare])
    return append_catalogue(w)


def expand_program(program_html: str):
    """Split a Program cell by <br>, strip tags, propagate composer prefix."""
    parts = re.split(r"<br\s*/?>", program_html)
    current_composer = None
    out = []
    for raw in parts:
        w = strip_tags(raw).strip()
        if not w:
            continue
        m = re.match(r"^([^\W\d_][^:\d\n]*?):\s+(.+)$", w, re.UNICODE)
        if m and m.group(1)[0].isupper() and len(m.group(1)) < 40:
            current_composer = m.group(1).strip()
            out.append(w)
        else:
            if current_composer:
                out.append(f"{current_composer}: {w}")
            else:
                out.append(w)
    return out


def main():
    with open(CONCERTS, encoding="utf-8") as f:
        concerts = f.read()
    with open(RANKING, encoding="utf-8") as f:
        ranking = f.read()

    global CAT_MAP
    CAT_MAP = build_cat_map(concerts)

    tbody_match = re.search(r"<tbody>(.*?)</tbody>", concerts, re.DOTALL)
    if not tbody_match:
        print("Could not find <tbody> in concerts file", file=sys.stderr)
        return 1
    tbody = tbody_match.group(1)
    rows = re.findall(r"<tr>.*?</tr>", tbody, re.DOTALL)

    # Capture any existing Wikipedia anchor wrappers in the ranking file so
    # we can re-apply them when rebuilding the tbody (otherwise every regen
    # silently strips the link layer). Key by work name — multiple works
    # can share the same anchor (e.g. Tristan und Isolde linked from both
    # the opera and the Vorspiel+Liebestod row), so a flat anchor→work dict
    # would lose entries to overwrite.
    work_link = {}
    for anchor, work in re.findall(
        r"<tr><td>\d+</td><td>(<a [^>]*>)(.+?)</a></td>",
        ranking,
    ):
        work_link[work] = anchor
        # Alias: catalogue-appended form so the anchor follows new opus suffixes
        appended = append_catalogue(work)
        if appended != work:
            work_link[appended] = anchor
        # Alias: historical "em-before-catalogue" → "catalogue-before-em"
        m = re.search(
            r",\s*(<em>[^<]+</em>)\s+(\b(?:op\.|KV|BWV|D\.|Hob\.|WAB|Sz\.|TrV|HWV)\s*\d+(?:[a-z]|:?\d+)*\b)",
            work,
        )
        if m:
            reordered = work[:m.start()] + " " + m.group(2) + ", " + m.group(1) + work[m.end():]
            work_link[reordered] = anchor

    work_counts = {}

    for row in rows:
        tds = re.findall(r"<td>(.*?)</td>", row, re.DOTALL)
        if len(tds) < 6:
            continue
        conductor = strip_tags(tds[4]).strip()
        program = tds[5]
        for w in expand_program(program):
            normalized = normalize_work(w)
            if is_placeholder(normalized):
                continue
            work_counts.setdefault(normalized, {})
            work_counts[normalized][conductor] = (
                work_counts[normalized].get(conductor, 0) + 1
            )

    ranked = [
        (work, sum(conductors.values()), conductors)
        for work, conductors in work_counts.items()
        if sum(conductors.values()) >= 2
    ]
    ranked.sort(key=lambda x: (-x[1], x[0]))

    if "--check" in sys.argv:
        for i, (work, total, conductors) in enumerate(ranked, 1):
            print(f"#{i} {work}: total={total}")
            for c, n in sorted(conductors.items(), key=lambda x: (-x[1], x[0])):
                print(f"   {c}: {n}")
        return 0

    new_rows = []
    prev_total = None
    current_rank = 0
    for position, (work, total, conductors) in enumerate(ranked, 1):
        if total != prev_total:
            current_rank = position
            prev_total = total
        lines = [
            f"{c}: {n}"
            for c, n in sorted(conductors.items(), key=lambda x: (-x[1], x[0]))
        ]
        cell = "<br>".join(lines)
        anchor = work_link.get(work, "")
        work_html = f"{anchor}{work}</a>" if anchor else work
        new_rows.append(
            f"<tr><td>{current_rank}</td><td>{work_html}</td><td>{total}</td><td>{cell}</td></tr>"
        )

    new_tbody = "<tbody>\n" + "\n".join(new_rows) + "\n</tbody>"
    ranking = re.sub(r"<tbody>.*?</tbody>", new_tbody, ranking, flags=re.DOTALL)

    with open(RANKING, "w", encoding="utf-8") as f:
        f.write(ranking)
    print(f"Wrote {RANKING} with {len(ranked)} ranked works.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
