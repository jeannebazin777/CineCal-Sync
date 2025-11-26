import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event
from datetime import datetime, date, timedelta
import calendar
import locale
import sys # Pour afficher les erreurs si le scraping échoue

# Configuration pour lire les noms de mois en français
try:
    locale.setlocale(locale.LC_TIME, 'fr_FR.UTF-8')
except:
    pass

BASE_URL = "https://www.cinematheque.fr/"

def get_next_months_urls(num_months=6):
    """Génère les URL des 6 prochains mois (MM-YYYY.html) à partir d'aujourd'hui."""
    urls = []
    current_date = date.today().replace(day=1)
    
    for _ in range(num_months):
        # Format MM-YYYY.html (ex: 11-2025.html, 12-2025.html)
        url_suffix = f"calendrier/{current_date.month:02d}-{current_date.year}.html"
        urls.append(BASE_URL + url_suffix)
        
        # Passage au mois suivant
        if current_date.month == 12:
            current_date = current_date.replace(year=current_date.year + 1, month=1)
        else:
            current_date = current_date.replace(month=current_date.month + 1)
            
    return urls

def scrape_event_details(seance_url):
    """Visite une page de séance individuelle et extrait les données propres du bouton 'data-'."""
    try:
        response = requests.get(seance_url, headers={'User-Agent': 'CineBot/1.0'})
        response.raise_for_status() # Lève une exception si le statut est 4xx ou 5xx
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Cible le bouton JS qui contient toutes les données formatées
        button = soup.find('button', class_='js-add-to-calendar')
        
        if button:
            return {
                'title': button.get('data-name'),
                'start_date': button.get('data-start-date'),
                'end_date': button.get('data-end-date'),
                'start_time': button.get('data-start-time'),
                'end_time': button.get('data-end-time'),
                'location': button.get('data-location'),
                'description': button.get('data-description').strip() if button.get('data-description') else '',
                'url': seance_url
            }
    except Exception as e:
        # sys.stderr.write(f"Erreur HTTP/Scraping sur {seance_url}: {e}\n")
        return None
    return None

def run_scraper():
    cal = Calendar()
    cal.add('prodid', '-//Cinémathèque Synchro (Bouton Data)//')
    cal.add('version', '2.0')
    cal.add('X-WR-CALNAME', 'Cinémathèque Française (Synchronisé)')
    
    month_urls = get_next_months_urls(6)
    seance_links = set()
    events_count = 0

    # 1. Première passe : Collecter les URL de toutes les séances à partir des pages mensuelles
    for url in month_urls:
        try:
            response = requests.get(url, headers={'User-Agent': 'CineBot/1.0'}, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Cibler les liens de séance sur la page calendrier
            links = soup.find_all('a', class_='show', href=True)
            for link in links:
                seance_links.add(BASE_URL + link['href'])
                
        except Exception:
            # On ignore les mois futurs qui ne sont pas encore publiés (page 404)
            continue

    # 2. Deuxième passe : Visiter chaque séance pour extraire les données propres et créer l'ICS
    for link in seance_links:
        details = scrape_event_details(link)
        
        if details and details.get('start_date') and details.get('start_time'):
            # *** DEBUT DU BLOC TRY/EXCEPT CORRIGÉ ***
            try:
                # Conversion des données formatées (YYY-MM-DD HH:MM)
                dt_start = datetime.strptime(f"{details['start_date']} {details['start_time']}", '%Y-%m-%d %H:%M')
                dt_end = datetime.strptime(f"{details['end_date']} {details['end_time']}", '%Y-%m-%d %H:%M')
                
                event = Event()
                event.add('summary', details['title'])
                event.add('dtstart', dt_start)
                event.add('dtend', dt_end)
                event.add('location', details['location'])
                event.add('url', details['url'])
                event.add('description', details['description'])
                event.add('uid', f"{dt_start.strftime('%Y%m%d%H%M')}-{details['title'][:10].replace(' ', '')}@cine.fr")
                cal.add_component(event)
                events_count += 1
                
            except Exception as e:
                # Gère les erreurs de conversion de format si une date est malformée
                sys.stderr.write(f"Erreur de conversion iCal pour {link}: {e}\n")
                continue
            # *** FIN DU BLOC TRY/EXCEPT CORRIGÉ ***

    # 3. Sauvegarde finale
    with open('feed.ics', 'wb') as f:
        f.write(cal.to_ical())
    
    print(f"Génération réussie de {events_count} événements.")

if __name__ == "__main__":
    # Assurez-vous d'avoir les bibliothèques installées (pip install requests beautifulsoup4 icalendar)
    run_scraper()