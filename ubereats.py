from playwright.sync_api import sync_playwright
import logging
import json
import re

logging.basicConfig(level=logging.DEBUG)

def get_query(key:str) -> str:
    baseurl = 'https://www.ubereats.com/search'
    dinning_mode = 'diningMode=DELIVERY' # or PICKUP
    pl = 'pl=JTdCJTIyYWRkcmVzcyUyMiUzQSUyMlBpdHRzYnVyZ2glMjIlMkMlMjJyZWZlcmVuY2UlMjIlM0ElMjJDaElKQTRVR1NHX3hOSWdSTkJ1aVdxRVYtWTAlMjIlMkMlMjJyZWZlcmVuY2VUeXBlJTIyJTNBJTIyZ29vZ2xlX3BsYWNlcyUyMiUyQyUyMmxhdGl0dWRlJTIyJTNBNDAuNDQwMzk1JTJDJTIybG9uZ2l0dWRlJTIyJTNBLTc5Ljk5NjE5NSU3RA%3D%3D'
    query = f'q={key}'
    search_config = 'sc=SEARCH_SUGGESTION&vertical=ALL'
    url = f'{baseurl}?{dinning_mode}&{pl}&{query}&{search_config}'
    return url

def check_json(response, results, suggestion_keys:list):
    """ Check JSON traffics """
    if response.url.split('/')[-1] == 'getFeedV1':
        # get desire items, the true data
        get_feed(response, results)
    elif response.url.split('/')[-1] == 'getSearchSuggestionsV1':
        # get suggestion for new queries or keywords
        get_suggestion(response, suggestion_keys)
    elif response.url.split('/')[-2] == 'api':
        # other api responses
        logging.debug(f'Passing {response.url}')
        pass
    else:
        # passing all non-json traffics
        pass

def get_feed(response, results):
    """ Get feed items from JSON - functional
    Get desire items, the true data.
    """
    try:
        data = response.json()
        items = data['data']['feedItems']
        for item in items:
            try:
                rating = float(item['store']['rating']['text'])
                n_rating = re.search(r'\d+\sreviews?', item['store']['rating']['accessibilityText']).group()
                n_rating = int(re.search(r'\d+', n_rating).group())
            except:
                rating = None
                n_rating = None
            url = 'https://www.ubereats.com' + item['store']['actionUrl']
            if url not in [item['url'] for item in results]:
                results.append(
                    {
                        'restaurant_name': item['store']['title']['text'],
                        'rating': rating,
                        'rating_count': n_rating,
                        'lon': item['store']['mapMarker']['longitude'],
                        'lat': item['store']['mapMarker']['latitude'],
                        'url': url
                    }
                )
    except Exception as e:
        logging.debug(f'Structure is different: {e}')
        pass

def get_suggestion(response, suggestion_keys:list):
    """ Get new keys - functional
    Get suggestion for new queries or keywords.
    """
    data = response.json()
    for item in data['data']:
        if item['type'] == 'text':
            new_key = item['title'].lower()
            if new_key not in suggestion_keys:
                suggestion_keys.append(new_key)
                logging.info(f'New sugession key = {new_key}')
            else:
                continue
        else:
            pass

def crawl(key:str, playwright):
    url = get_query(key)
    results = []
    suggestion_keys = [key]
    scraped_keys = []
    browser = playwright.chromium.launch()
    page = browser.new_page()
    page.on('response', lambda response: check_json(response, results, suggestion_keys))
    page.goto(url)
    page.wait_for_selector('div[data-test=feed-desktop]')
    page.wait_for_load_state()
    page.locator('button', has_text='Show more').click()
    page.wait_for_load_state()
    scraped_keys.append(key)
    new_keys = suggestion_keys
    for key in new_keys:
        if key not in scraped_keys:
            page.goto(get_query(key))
            page.wait_for_selector('div[data-test=feed-desktop]')
            page.wait_for_load_state()
            scraped_keys.append(key)
    logging.info(f'Scraped keys = {", ".join(scraped_keys)}')
    browser.close()
    return results

def parse_modifier(page, item):
    item.query_selector('div').hover
    page.mouse.click()
    page.wait_for_load_state()
    for item_mod in page.query_selector_all('ul > li'):
        print(item_mod.inner_html())
        #modifier_title = item_mod.query_selector('div')
        #modifier_title = modifier_title.query_selector('div > div').inner_text()
        #print(modifier_title.upper())
        #modifier_list = item_mod.query_selector_all('label')
        #for modifier in modifier_list:
        #    dot_modifier = modifier.query_selector('div > div > div > div > div').inner_text()
        #    print(dot_modifier)
    page.go_back()

def parse(page):
    all_menu = []
    menu_selector = '#main-content > div:nth-child(5) > div > div > ul > li'
    page.wait_for_selector(menu_selector, timeout=45000)
    container_tags = page.query_selector('#main-content > div:nth-child(4) > div > div:nth-child(1) > div:nth-child(3)')
    tags = container_tags.query_selector('div.ah > div')
    tags = tags.inner_text()
    tags = tags.split(chr(8226)) # chr(8226) = '\u2022' = dot
    tags = ', '.join([tag.strip() for tag in tags if not re.findall(f'rating', tag)])
    menu_list = page.query_selector_all(menu_selector)
    for li in menu_list:
        category_name = li.query_selector('div').inner_text()
        for item in li.query_selector_all('ul > li'):
            
            # handle menu item
            menu_item = item.query_selector_all('span')
            menu_item = [span.inner_text() for span in menu_item]
            menu_item_name = menu_item[0]
            menu_item_price = menu_item[1]
            menu_item_description = menu_item[2] if len(menu_item) >= 3 else None
            
            # collect all data
            all_menu.append(
                {
                    'category_name': category_name,
                    'menu_item_name': menu_item_name,
                    'menu_item_description': menu_item_description,
                    'menu_item_price': menu_item_price,
                    'restaurant_tags': tags,
                    'restaurant_url': page.url,
                }
            )

        # handle modifier in menu item
        # not complete
        # parse_modifier(page, item)

    logging.info(f'Scraped {page.url}')
    return all_menu

def scrape(urls:list, playwright):
    results = []
    browser = playwright.chromium.launch(headless=False)
    page = browser.new_page()
    for url in urls:
        try:
            page.goto(url, timeout=120000)
            if page.locator('div[role=dialog]').is_visible():
                page.wait_for_selector('div[role=dialog]', timeout=60000)
                page.locator('button[aria-label=Close]').click()
                data = parse(page)
            else:
                data = parse(page)
            results += data
        except Exception as e:
            logging.error(f'Connot scrape {url}: {e}')
            continue
    #for url in urls:
    #    page.goto(url, timeout=120000)
    #    def handle_popup(popup):
    #        popup.wait_for_load_state()
    #        page.locator('button[aria-label=Close]').click()
    #        logging.debug('Popup closed')
    #    page.on('popup', handle_popup)
    #    data = parse(page)
    #    results += data

    browser.close()
    return results

with sync_playwright() as playwright:
    #key = 'mediterranean'
    #data = crawl(key, playwright)
    #logging.info(f'Data collected = {str(len(data))}')
    #with open('result.json', 'w') as fout:
    #    json.dump(data, fout, indent=2)
    #fout.close()
    with open('result.json', 'r') as fin:
        urls = [item.get('url') for item in json.load(fin)][:100]
    #urls = [
    #    'https://www.ubereats.com/store/ege-mediterranean/I0SF3e1iSVyRozdJbLTmtw',
    #    'https://www.ubereats.com/store/jolinas-mediterranean-cuisine/Swp0WGbCShO22eTzvXaJ8A',
    #    'https://www.ubereats.com/store/la-madina-mediterranean-food/PEDs6oYAX7CHlbHydn91uA',
    #    'https://www.ubereats.com/store/panera-5430-centre-avenue/1sO6bm47TsO2aZ7GjzwY0A'
    #]
    results = scrape(urls, playwright)
    with open('stores.json', 'w') as fout:
        json.dump(results, fout, indent=2)
    fout.close()

