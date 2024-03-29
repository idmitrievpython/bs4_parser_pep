import csv
import logging
import re
import requests_cache

from bs4 import BeautifulSoup
from urllib.parse import urljoin
from tqdm import tqdm
from configs import configure_argument_parser, configure_logging
from constants import (
    BASE_DIR,
    LATEST_VERSION_RESULT,
    MAIN_DOC_URL,
    PEP_DOC_URL,
    WHATS_NEW_RESULT
)
from utils import get_response, find_tag
from outputs import control_output


def pep(session):
    response = get_response(session, PEP_DOC_URL)

    if response is None:
        return

    soup = BeautifulSoup(response.text, 'lxml')
    pep_common_list = soup.find_all('section', {'id': 'numerical-index'})
    pattern = r'(.*)\, (.*)'
    pep_status = {'total': 0}
    for pep_one in pep_common_list:
        tr_tag = pep_one.find_all('tr')
        for tr in tr_tag[1:]:
            text_title = re.search(pattern, tr.abbr['title'])
            url_one = urljoin(PEP_DOC_URL, tr.a['href'])
            response_one = get_response(session, url_one)
            soup = BeautifulSoup(response_one.text, 'lxml')
            pep_content = soup.find('section', {'id': 'pep-content'})
            abbr_tg = pep_content.find_all('abbr')
            pep_status_card = abbr_tg[0].text
            pep_status_list = text_title.group(2)
            pep_status[pep_status_card] = pep_status.get(pep_status_card,
                                                         0) + 1
            if pep_status_list != pep_status_card:
                logging.info(
                    f'Несовпадающие статусы: {url_one}. '
                    f'Статус в карточке: {pep_status_card}. '
                    f'Ожидаемые статусы: ["{pep_status_list}"]'
                )
    pep_status_dict = []
    pep_status_dict.extend(pep_status.items())

    downloads_dir = BASE_DIR / 'results'
    downloads_dir.mkdir(exist_ok=True)
    file_name = 'list_status.csv'
    file_path = downloads_dir / file_name

    with open(file_path, 'w', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerows(pep_status_dict)


def whats_new(session):
    whats_new_url = urljoin(MAIN_DOC_URL, 'whatsnew/')
    response = get_response(session, whats_new_url)

    if response is None:
        return

    soup = BeautifulSoup(response.text, features='lxml')
    main_div = find_tag(soup, 'section', attrs={'id': 'what-s-new-in-python'})
    div_with_ul = find_tag(main_div, 'div', attrs={'class': 'toctree-wrapper'})
    sections_by_python = div_with_ul.find_all(
        'li', attrs={'class': 'toctree-l1'}
    )
    result = WHATS_NEW_RESULT
    for section in tqdm(sections_by_python):
        version_a_tag = section.find('a')
        href = version_a_tag['href']
        version_link = urljoin(whats_new_url, href)
        response = get_response(session, version_link)

        if response is None:
            continue

        soup = BeautifulSoup(response.text, 'lxml')
        h1 = find_tag(soup, 'h1')
        dl = find_tag(soup, 'dl')
        dl_text = dl.text.replace('\n', ' ')
        result.append(
            (version_link, h1.text, dl_text)
        )
    return result


def latest_versions(session):
    response = get_response(session, MAIN_DOC_URL)
    soup = BeautifulSoup(response.text, 'lxml')

    if response is None:
        return

    sidebar = find_tag(soup, 'div', attrs={'class': 'sphinxsidebarwrapper'})

    ul_tags = sidebar.find_all('ul')

    for ul in ul_tags:
        if 'All version' in ul.text:
            a_tags = ul.find_all('a')
            break
    else:
        raise Exception('Тэг <a> с текстом "All version" не найден')

    results = LATEST_VERSION_RESULT
    pattern = r'Python (?P<version>\d\.\d+) \((?P<status>.*)\)'
    for a_tag in a_tags:
        link = a_tag['href']
        text_match = re.search(pattern, a_tag.text)
        if text_match is not None:
            version = text_match.group('version')
            status = text_match.group('status')
        else:
            version = a_tag.text
            status = ''
        results.append(
            (link, version, status)
        )
    return results


def download(session):
    downloads_url = urljoin(MAIN_DOC_URL, 'download.html')
    response = get_response(session, downloads_url)

    if response is None:
        return

    soup = BeautifulSoup(response.text, 'lxml')
    table_tag = find_tag(soup, 'table', attrs={'class': 'docutils'})
    pdf_a4_tag = find_tag(
        table_tag, 'a', attrs={'href': re.compile(r'.+pdf-a4\.zip$')}
    )

    pdf_a4_link = pdf_a4_tag['href']
    archive_url = urljoin(downloads_url, pdf_a4_link)

    filename = archive_url.split('/')[-1]

    downloads_dir = BASE_DIR / 'downloads'
    downloads_dir.mkdir(exist_ok=True)
    archive_path = downloads_dir / filename

    response = session.get(archive_url)

    with open(archive_path, 'wb') as file:
        file.write(response.content)

    logging.info(f'Архив был загружен и сохранён: {archive_path}')


MODE_TO_FUNCTION = {
    'whats-new': whats_new,
    'latest-versions': latest_versions,
    'download': download,
    'pep': pep
}


def main():
    configure_logging()
    logging.info('Парсер запущен!')
    arg_parser = configure_argument_parser(MODE_TO_FUNCTION.keys())
    args = arg_parser.parse_args()
    logging.info(f'Аргументы командной строки: {args}')

    session = requests_cache.CachedSession()
    if args.clear_cache:
        session.cache.clear()

    parser_mode = args.mode
    results = MODE_TO_FUNCTION[parser_mode](session)

    if results is not None:
        control_output(results, args)

    logging.info('Парсер завершил работу.')


if __name__ == '__main__':
    main()
