# kayjuubee · Hotfolder → USB

Windows-Anwendung für dslrBooth: Neue Veranstaltungsdateien im Hintergrund auf USB-Sticks verteilen. Original-Logo, dunkle Oberfläche, manuelle Veranstaltungsauswahl, Tray-Symbol und Kopierprotokoll.

## Start und Windows-EXE

Für den Start aus dem Quellcode: Python 3.12 mit Tcl/Tk und Python Launcher installieren, dann `py -3 -m pip install -r requirements.txt` und `Starten.bat` ausführen.

`Bauen.bat` erstellt unter Windows eine eigene virtuelle Umgebung, installiert die Bauabhängigkeiten und erzeugt `dist/kayjuubee-USB.exe`. Diese EXE enthält Python, Logo und Bibliotheken; auf dem Booth-Rechner ist keine separate Python-Installation nötig. Alternativ im GitHub-Reiter Actions den Workflow **Windows EXE** manuell starten und anschließend das Artefakt herunterladen. Der Workflow steht erst nach Hochladen der Projektänderungen zur Verfügung. Eine Windows-EXE kann in der Linux-Entwicklungsumgebung nicht gebaut oder getestet werden. Das Programm ist noch nicht digital signiert.

## Veranstaltung und Kopieren

Nach jedem Start bleibt die Veranstaltung bewusst **unausgewählt**, auch nach einem Absturz. Manuell im Dropdown oder per „Neueste Veranstaltung auswählen“ wählen. Dieser Knopf verwendet das Windows-Erstellungsdatum, nicht den Datumspräfix. Der Überordner ist standardmäßig `C:\dslrBooth` und lässt sich ändern. „Aktualisieren“ erhält eine noch vorhandene Auswahl. Kein automatischer Wechsel auf neue Veranstaltungen.

`Originals` und `Prints` sind vorausgewählt. `thumbs` unter Prints ist ausgeschlossen und separat zuschaltbar. Andere vorhandene Veranstaltungsordner können ebenfalls ausgewählt werden. Zielstruktur: `<USB>/<Veranstaltung>/<Ordner>/…`.

Prüfintervall: 1 bis 1440 Minuten (Standard 5), mit „Intervall übernehmen“ aktivieren. „Jetzt alle kopieren“ startet unmittelbar für die ausgewählten Ordner, auch bei pausierter Automatik. Es gibt nur einen Kopiervorgang gleichzeitig. Die Pause beendet keinen laufenden Durchlauf.

Im normalen Betrieb werden vorhandene Zieldateien nicht überschrieben oder gelöscht. Eine Ausnahme ist die unten beschriebene vollständige Neukopie auf einen Ersatz-Stick nach fünf gleichen Kopierfehlern. Gleicher Dateiname gilt als vorhanden, auch bei unterschiedlichem Inhalt. Dateien mit weniger als zehn Sekunden altem Änderungsdatum sowie während des Lesens veränderte Dateien werden zurückgestellt. Fertige Dateien werden auf dem Ziel zunächst temporär geschrieben und anschließend veröffentlicht; Verknüpfungen werden nicht kopiert. Quelle und Ziel dürfen sich nicht überlappen.

## USB-Wiedererkennung und voller Stick

Windows-Wechseldatenträger werden alle drei Sekunden erkannt. Die Volume-Kennung erhält die Auswahl auch bei einem geänderten Laufwerksbuchstaben. Ein unbekannter anderer Stick wird bei verlorener Auswahl nicht automatisch beschrieben. Bei der allerersten Auswahl wird der erste verfügbare Stick verwendet; Ziel vor dem Start prüfen. Manche USB-Festplatten melden sich als festes Laufwerk und erscheinen deshalb nicht. Nach Formatierung kann sich die Volume-Kennung ändern.

Vor jeder Datei wird geprüft, ob ausreichend Platz plus 1 MiB Reserve vorhanden ist. Wird der Stick voll oder passt die nächste Datei nicht, greift die unten beschriebene Wiederholung: fünf gleiche Fehler führen zum Stopp und zur Anforderung eines anderen Sticks. **Keine Popups, Tray-Benachrichtigungen, Töne oder automatisches Öffnen des Fensters.** Die Meldung steht ausschließlich im Programmfenster und im Protokoll.

1. Ersten Stick sicher entfernen, nachdem der Kopiervorgang angehalten hat.
2. Zweiten Stick anschließen und im USB-Dropdown auswählen.
3. „Mit diesem Stick fortsetzen“ drücken. Nach fünf gleichen Fehlern beginnt sofort eine vollständige Neukopie der Veranstaltung auf dem anderen Stick.

Ein lokales SQLite-Protokoll merkt sich erfolgreich kopierte Quelldateien anhand ihres vollständigen Pfades, ihrer Größe und ihres Änderungsdatums. Bei einem freiwilligen Stickwechsel werden nur noch nicht übertragene Dateien kopiert. **Nach fünf gleichen Kopierfehlern wird dagegen die gesamte Veranstaltung mit den zuvor ausgewählten Ordnern auf dem Ersatz-Stick erneut kopiert.** Das Protokoll gilt auch nach einem Programmneustart. Originaldateien auf dem Rechner bleiben erhalten. Das Entfernen einer bereits kopierten Datei vom USB-Stick führt nicht zur erneuten Übertragung, solange sie im lokalen Protokoll steht. Die lokale Datenbank darf daher während einer Veranstaltung nicht gelöscht werden. Schon vor Verwendung dieser Anwendung auf einen Stick kopierte Dateien werden nicht automatisch in dieses Protokoll aufgenommen.

## Tray, Fortschritt und Protokoll

Minimieren und das Schließen-Kreuz verstecken das Fenster im Tray neben der Windows-Uhr; Kopieren läuft weiter. Über das Tray-Menü „Programm öffnen“ oder „Beenden“ wählen. Falls Windows das Symbol ausblendet, befindet es sich unter dem Pfeil für ausgeblendete Symbole. Ist der Tray nicht verfügbar, bleibt das Programm minimiert in der Taskleiste erreichbar. „Programm beenden“ beendet es vollständig und bricht gegebenenfalls die laufende Datei sicher ab.

Die Anzeige zeigt Dateiname, übertragene MiB, Dateifortschritt, Anzahl neu kopierter Dateien im aktuellen Durchlauf und Ergebnis des letzten Versuchs. „Protokoll anzeigen“ öffnet ein aktualisierbares Protokoll. Fehler und abgeschlossene Dateien werden mit Zeitstempel gespeichert. Das Log rotiert ab 2 MB; drei Sicherungen werden aufbewahrt.

Einstellungen, Kopierhistorie und Protokoll liegen in `%LOCALAPPDATA%\HotfolderUSB`. Quellordner, angewendetes Intervall, Kopiertempo und USB-Kennung werden beim Verbergen oder Beenden gespeichert. Die Veranstaltung wird bewusst nicht gespeichert. Der optionale Booth-Autostart ist unten beschrieben.

## Vorrang für dslrBooth

Im standardmäßigen schonenden Modus nutzt der Windows-Prozess `BELOW_NORMAL_PRIORITY_CLASS`, der Kopierthread zusätzlich `THREAD_MODE_BACKGROUND_BEGIN` für niedrige CPU-, I/O- und Speicherpriorität. Kann dieser Threadmodus nicht aktiviert werden, beginnt das Kopieren nicht. Im schonenden Modus ist die Geschwindigkeit auf 1 bis 64 MiB/s einstellbar (Standard 16); Änderungen wirken ab dem nächsten Durchlauf. Der zusätzliche Modus „Volle Kopierleistung“ ist unten beschrieben. 256-KiB-Blöcke und Pausen begrenzen Speicher und Übertragungsrate. dslrBooth-Prozesse und Einstellungen werden nicht verändert. Gemeinsam genutzte Hardware kann dennoch beeinflusst werden; Aufnahmebetrieb und USB-Wechsel müssen auf dem Zielrechner geprüft werden.

## Entwicklung und Logo

`python -m unittest discover -s tests -v` prüft unter anderem Ordnerfilter, Wiederholung, vollen Stick, Fortsetzung auf Stick 2, persistente Historie, Schreibfehler und Abbruch. Windows-spezifische USB- und Tray-Funktionen erfordern einen Hardwaretest unter Windows.

Das Original-Logo liegt fest in `assets/kayjuubee.png` und wird proportional dargestellt. Es werden keine externen Bilder oder Schriftarten nachgeladen. Nach einem Absturz können `.hotfolder-*`-Dateien auf dem USB-Stick übrig bleiben; bei beendetem Programm können diese gelöscht werden.

## Automatisch mit der Booth-Software starten

Die Option **„Mit dslrBooth / lumaBooth starten (Windows)“** einmal im Programm aktivieren. Sie registriert einen kleinen Wächter für den aktuellen Benutzer unter `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`; Administratorrechte sind nicht erforderlich. Der Wächter wird sofort und künftig bei der Windows-Anmeldung gestartet. Er prüft alle drei Sekunden ausschließlich die Namen laufender Prozesse (`dslrBooth.exe`, `lumaBooth.exe`, `luma booth.exe`), ohne auf die Booth-Anwendung zuzugreifen oder deren Einstellungen zu ändern.

Sobald eine Booth-Sitzung beginnt, startet er den Kopierer einmalig **im Tray ohne Fokusübernahme**. Es gibt keine doppelte Programminstanz. Manuelles Beenden bleibt wirksam, bis alle Booth-Prozesse beendet und erneut gestartet wurden. Das Beenden der Booth-Software beendet einen laufenden Kopiervorgang nicht. Die Veranstaltung muss weiterhin bewusst ausgewählt werden. Deaktivieren der Option entfernt den Autostarteintrag und beendet den Wächter beim nächsten Prüfintervall. Nach Verschieben der EXE Autostart am neuen Ort erneut aktivieren.

Dies gilt für Software auf demselben Windows-PC. Der Start von lumaBooth auf einem iPad kann damit nicht erkannt werden.

## Fehler bleiben im Hintergrund

Auch Fehler beim Kopieren, bei USB-Erkennung und bei Oberflächenaktionen erzeugen keine Dialoge, Töne oder Fokuswechsel. Sie werden im Fensterstatus und im Protokoll erfasst. Windows-Dialoge für fehlende Medien und Prozessfehler werden für diesen Prozess unterdrückt. Startfehler werden nach Möglichkeit in `startup-error.log` gespeichert. Das Programm nimmt niemals automatisch das Fenster nach vorn; das geschieht ausschließlich über „Programm öffnen“ im Tray-Menü.

## Inhaltsprüfung, Übersicht und Countdown

**„Dateiinhalt nach dem Kopieren prüfen“** vergleicht SHA-256-Prüfsummen der gelesenen Quelldaten und der zurückgelesenen temporären Zieldatei, bevor die Datei endgültig veröffentlicht und als übertragen verbucht wird. Bei Abweichung wird die temporäre Datei entfernt und der Durchlauf mit einer stillen Fehlermeldung beendet. Die Prüfung ist optional, benötigt zusätzliche Lesezeit und nutzt dieselbe Drosselung und Hintergrundpriorität. Sie gilt für neue Kopien ab Aktivierung, nicht rückwirkend für bereits protokollierte Dateien. Die Einstellung wird gespeichert.

**„Veranstaltungsübersicht“** zeigt für die gerade ausgewählten Ordner die Anzahl der Quelldateien, protokolliert übertragene Dateien je Stick inklusive Datenmenge und Anzahl der inhaltlich geprüften Dateien sowie Dateien ohne Übertragungsnachweis. Bis zu 500 dieser Dateinamen werden angezeigt. Die gespeicherte Stick-Bezeichnung hilft beim Zuordnen bereits entfernter Sticks. Die Übersicht beruht auf der lokalen Historie und dem aktuellen Quellbestand; sie behauptet keine erneute Prüfung nicht angeschlossener Sticks. Vor Verwendung der Anwendung bereits vorhandene Zieldateien besitzen gegebenenfalls keinen Übertragungsnachweis. Die Ausnahme für die vollständige Neukopie nach fünf Fehlern ist unten beschrieben. Die Übersicht wird auf Knopfdruck im Hintergrund berechnet. Wird das Programm währenddessen verborgen, öffnet sie kein Fenster.

Der **Countdown** zeigt die Zeit bis zur nächsten automatischen Prüfung. Ohne Veranstaltung, während einer Kopie, bei Pause oder beim Warten auf einen Ersatz-Stick wird stattdessen der passende Zustand angezeigt. Ein Sofortdurchlauf verschiebt den regulären Timer nicht.

## Stick sicher entfernen

„Stick sicher entfernen“ pausiert zunächst die Automatik und bricht eine gerade bearbeitete Datei sauber ab. Bereits fertig kopierte Dateien bleiben erhalten, unvollständige temporäre Dateien werden nach Möglichkeit entfernt. Danach fordert das Programm Windows auf, ausschließlich das ausgewählte Volume zu sperren, Schreibpuffer zu leeren, das Volume auszuhängen und das Medium auszuwerfen. Bei offenen Dateien anderer Programme wird nichts erzwungen. Geräte oder Rechte, die diesen Vorgang nicht unterstützen, führen zu einer stillen Fehlermeldung; dann die Windows-Funktion zum sicheren Entfernen verwenden. Die Erfolgsmeldung erscheint erst nach erfolgreichem Windows-Aufruf. Die Automatik bleibt nach dem Auswerfen oder einem Auswurffehler pausiert.

Nach Einsetzen eines zweiten Sticks diesen im Dropdown wählen und **„Mit diesem Stick fortsetzen“** drücken: Das startet sofort die Kopie und aktiviert die Automatik wieder. Nach fünf gleichen Kopierfehlern wird die ganze Veranstaltung erneut übertragen; bei einem freiwilligen Wechsel nur der Rest. Die lokale Übertragungshistorie bleibt dabei erhalten.

`Bauen.bat` und der GitHub-Workflow führen vor dem Verpacken die Tests und anschließend einen Selbsttest der erzeugten EXE aus (Logo/Tk, Tray-Backend-Import, Kopieren, Inhaltsprüfung, Historie und Windows-Prozesserkennung). `self-test-report.json` dokumentiert diese Prüfungen. Der Selbsttest schreibt nicht auf USB-Sticks. Die Hardware-Prüfschritte stehen in [PRAXISTEST.md](PRAXISTEST.md); sie wurden in der Linux-Umgebung nicht ausgeführt.


## Restmenge, Restzeit und volle Kopierleistung

Beim Kopierstart wird die Menge der aktuell kopierbaren Dateien ermittelt: Bereits vorhandene Zieldateien und protokollierte Kopien zählen im normalen Betrieb nicht dazu. Die Anzeige nennt verbleibende Dateien, MiB/GiB und eine aus dem bisherigen Durchsatz geschätzte Restzeit. Die optionale Inhaltsprüfung wird in der Zeitberechnung berücksichtigt. Die Schätzung erscheint nach mindestens einer Sekunde gemessener Arbeit; beim Start ist sie noch unbekannt. Der aktuelle Durchlauf arbeitet auf einem Bestand zum Startzeitpunkt. Später eintreffende und noch geschriebene Dateien werden beim nächsten Durchlauf berücksichtigt. Zurückgestellte Dateien werden separat ausgewiesen. USB-Schreibpuffer, Dateigrößen und zusätzliche Last können die Schätzung verändern.

**„Volle Kopierleistung“** entfernt alle künstlichen Kopierpausen und verwendet 1-MiB-Blöcke. Während der Kopie läuft der Prozess mit normaler Windows-Priorität und der Kopierthread ohne Hintergrunddrosselung. Nach Abschluss, Fehler oder Abbruch wird die niedrige Prozesspriorität wiederhergestellt. Hohe oder Echtzeitpriorität wird nicht verwendet. Das tatsächliche Tempo hängt von Rechner, Quelle und USB-Stick ab. Integritätsprüfung, temporäres Schreiben, USB-Kennungsprüfung, Abbruch und Fehlerbehandlung bleiben aktiv. Dieser Modus kann die Booth-Software beeinträchtigen und ist für Zeiten ohne Aufnahmebetrieb gedacht. Er gilt ab dem nächsten Kopierstart und ist bei jedem Programmneustart ausgeschaltet.

## Fünf gleiche Fehler und vollständige Neukopie

Kopierbezogene Betriebssystemfehler und fehlgeschlagene Inhaltsprüfungen werden automatisch erneut versucht, mit drei Sekunden Abstand. Nach dem fünften Auftreten desselben Fehlers innerhalb eines Durchlaufs wird endgültig angehalten. Windows-/Betriebssystem-Fehlercodes werden zum Vergleichen verwendet; bei Fehlern ohne Code zählt der Fehlertyp samt Meldung. Derselbe Fehler wird auch dann mitgezählt, wenn zwischendurch ein anderer Fehler auftritt. Abbruch und sicheres Entfernen unterbrechen die Wiederholungen sofort. Fehler beim Initialisieren der lokalen Datenbank oder der Priorisierung werden separat protokolliert.

Dann gilt:

1. Kein Popup, Ton, Fokuswechsel oder automatisches Öffnen des Fensters.
2. Im Status und Protokoll steht die Aufforderung, einen **anderen** Stick anzuschließen. Der bisherige Stick wird anhand der Volume-Kennung abgewiesen, auch bei geändertem Laufwerksbuchstaben.
3. „Mit diesem Stick fortsetzen“ startet auf dem anderen Stick die **gesamte Veranstaltung mit der ursprünglichen Ordnerauswahl**, nicht nur den Rest. Die bisherige Historie verhindert diese Neukopie nicht.
4. Bei dieser ausdrücklichen Fehler-Neukopie werden auch gleichnamige Dateien im Veranstaltungsordner des Ersatz-Sticks durch frisch kopierte Quelldateien ersetzt. Andere Dateien und andere Veranstaltungen werden nicht gelöscht. Bereits in derselben Neukopie erfolgreich geschriebene Dateien werden bei einem Wiederholungsversuch nicht nochmals geschrieben.
5. Der erforderliche Stickwechsel wird lokal gespeichert. Nach einem Programmneustart bleibt die Veranstaltung zunächst unausgewählt; bei erneuter Auswahl der betroffenen Veranstaltung gilt der Ersatz-Stick-Zwang weiterhin. Nach erfolgreicher Neukopie wird dieser Zustand aufgehoben.

Die Originaldateien bleiben unverändert. Die Neubeschreibung eines Ersatz-Sticks nach fünf Fehlern ersetzt die bisherige reine Restdatei-Fortsetzung für genau diesen Fehlerfall.
