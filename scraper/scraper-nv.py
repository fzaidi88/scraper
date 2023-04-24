"""
This program scrapes data from the website of the
Nevada State Board of Veterinary Medical Examiners

Outputs a CSV of a list of Examiners and related
data on Licenses, Notices, Restrictions and Findings,
and Places of Work
"""

from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.common.by import By
from selenium import webdriver
from bs4 import BeautifulSoup
import pandas as pd
import logging
import time
import os

EXAMINERS_FILENAME = 'nv-examiners.csv'
LICENSES_FILENAME = 'nv-examiner-licenses.csv'
NOTICES_FILENAME = 'nv-examiner-notices.csv'
WORKPLACES_FILENAME = 'nv-examiner-workplaces.csv'
FACILITIES_FILENAME = 'nv-facilities.csv'
FACILITY_PROFILES_FILENAME = 'nv-facility-profiles.csv'

# Set the logging level to WARNING
logging.basicConfig(level=logging.WARNING)

class UnexpectedColumnsError(Exception):
    pass

class InsufficientDataError(Exception):
    pass

class WebDriverWaitError(Exception):
    pass

def init_driver(headless=True):
    # Set up Selenium webdriver
    options = Options()
    options.add_argument('--disable-gpu')
    if headless:
        options.add_argument('--headless')  # Run Chrome in headless mode (no GUI)
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def load_element_by_tag(driver, url, tag_name='body', wait_seconds_max=5):
    driver.get(url)
    time.sleep(1.25)
    element = WebDriverWait(driver, wait_seconds_max).until(
        expected_conditions.presence_of_element_located((By.TAG_NAME, tag_name))
    )
    return element

def load_elements_by_tag(driver, url, tag_name='body', wait_seconds_max=5):
    driver.get(url)
    time.sleep(1)
    _ = WebDriverWait(driver, wait_seconds_max).until(expected_conditions.presence_of_element_located((By.TAG_NAME, tag_name)))
    elements = driver.find_elements(By.TAG_NAME, tag_name)
    return elements

def get_results_count(driver):
    elements_span = driver.find_elements(By.TAG_NAME, 'span')
    results_text = [e for e in elements_span if e.get_attribute('ng-if') == 'resultCount > 10'][0]
    print(results_text)
    results_count = results_text
    return results_count

def get_rows(table):
    # Get all table rows
    tbody = table.find_element(By.TAG_NAME, 'tbody')
    trs = tbody.find_elements(By.TAG_NAME, 'tr')
    row_count = len(trs)
    if row_count == 1:
        print(trs[0].get_attribute('innerHTML').strip())
        raise InsufficientDataError('Not enough data rows in the source.')
    return trs

def get_href(td):
    element_a = td.find_element(By.TAG_NAME, 'a')
    href = element_a.get_attribute('href')
    return href

def get_row_data(row):
    row_data = []
    elements_td = row.find_elements(By.TAG_NAME, 'td')
    for i, td in enumerate(elements_td):
        if i == 4:
            row_data.append(get_href(td))
        else:
            row_data.append('')
    return row_data

def get_page_urls(page_table):
    page_urls = []
    rows = get_rows(page_table)
    for row in rows:
        row_data = get_row_data(row)
        page_urls.append(row_data[4])
    return page_urls

def get_page_df(driver, page_url, results_start):
    page_table = load_element_by_tag(driver, page_url, 'table')
    page_df = pd.read_html(page_table.get_attribute('outerHTML'))[0].drop('Unnamed: 4', axis=1)
    # if results_start == 0:
    #     page_df.drop(0, axis=0, inplace=True)
    page_urls = get_page_urls(page_table)
    page_df['profile_url'] = pd.Series(page_urls)
    return page_df

def get_profile_tables(driver, url):
    tables = load_elements_by_tag(driver, url, 'table')
    dfs = []
    for t in tables:
        df = pd.read_html(t.get_attribute('outerHTML'))[0]
        dfs.append(df)
    return dfs

def load_search_results(driver, base_url, output_filename):
    examiners = pd.DataFrame(columns=['Last Name', 'First Name', 'License Category', 'Restrictions and/or Findings', 'profile_url'])
    total_results_count = 320 # 320 facilities, 5124 examiners # todo: get_results_count(driver)
    results_per_page = 100

    dfs = []
    for results_start in range(0, total_results_count, results_per_page):
        page_url = f'{base_url}/{results_start}/{results_per_page}'
        page_df = get_page_df(driver, page_url, results_start)
        dfs.append(page_df)

    output_df = pd.concat(dfs).reset_index(drop=True)
    print(f'Loaded {len(output_df)} search results. Last 5 are:')
    print(output_df[-5:])
    output_df.to_csv(output_filename)

def load_examiner_profiles(driver):
    examiners = pd.read_csv(EXAMINERS_FILENAME)
    with open(LICENSES_FILENAME, 'w') as f:
        f.write('')
    with open(NOTICES_FILENAME, 'w') as f:
        f.write('')
    with open(WORKPLACES_FILENAME, 'w') as f:
        f.write('')
    for i, profile_url in enumerate(examiners['profile_url']):
        print(i+1, profile_url)

        # get top section
        body = load_element_by_tag(driver, profile_url)
        elements = body.find_elements(By.XPATH, "//div[@class='col-md-8 col-sm-8 ng-binding']")
        profile_names = [e.get_attribute('innerHTML').strip() for e in elements]

        # get tables
        profile_tables = get_profile_tables(driver, profile_url)
        
        for t in profile_tables:
            # license_df = profile_tables[0]
            t['first_name'] = profile_names[0]
            t['last_name'] = profile_names[1]
            t['prev_name'] = profile_names[2]
            t['profile_url'] = profile_url
        with open(LICENSES_FILENAME, 'a') as f:
            output_df = profile_tables[0].reindex(columns=['first_name', 'last_name', 'prev_name', 'License Number', 'License Category', 'License Status', 'Initial Licensure Date', 'License Expiry Date', 'profile_url'])
            if i == 0:
                output_df.to_csv(f, index=False)
            else:
                output_df.to_csv(f, index=False, header=False, mode='a')
        with open(NOTICES_FILENAME, 'a') as f:
            output_df = profile_tables[1].reindex(columns=['first_name', 'last_name', 'prev_name', 'Type', 'Effective Date', 'Summary', 'Completion Date', 'Attachments', 'profile_url'])
            if i == 0:
                output_df.to_csv(f, index=False)
            else:
                output_df.to_csv(f, index=False, header=False, mode='a')
        with open(WORKPLACES_FILENAME, 'a') as f:
            output_df = profile_tables[2].reindex(columns=['first_name', 'last_name', 'prev_name', 'Name', 'Street Address', 'City', 'Postal Code', 'Start Date', 'End Date', 'profile_url'])
            if i == 0:
                output_df.to_csv(f, index=False)
            else:
                output_df.to_csv(f, index=False, header=False, mode='a')

def load_facility_profiles(driver):
    facilities = pd.read_csv(FACILITIES_FILENAME)
    with open(FACILITY_PROFILES_FILENAME, 'w') as f:
        f.write('')

    profiles = []
    for i, profile_url in enumerate((facilities['profile_url'])):
        # print(i+1, profile_url)
        facility = {
            'Name': '',
            'License Number': '',
            'Practice Type': '',
            'License Status': '',
            'Initial Licensure Date': '',
            'License Expiry Date': '',
            'Address Line 1': '',
            'Address Line 2': '',
            'City': '',
            'State': '',
            'Zip Code': '',
            'Telephone': '',
            'Fax': '',
            'profile_url': profile_url
        }
        body = load_element_by_tag(driver, profile_url)

        # facility name
        h2 = body.find_elements(By.XPATH, "//h2")
        facility['Name'] = h2[0].get_attribute('innerHTML').strip()
        
        # faciltiy details
        # rows = body.find_elements(By.XPATH, "//div[@class='row']")
        expected_labels = list(facility.keys())[1:-1]
        labels = body.find_elements(By.XPATH, "//label")
        labels_text = [l.get_attribute('innerHTML').strip().replace(':', '') for l in labels]
        if labels_text != expected_labels:
            print('ERR: Labels mismatch!')

        values = body.find_elements(By.XPATH, "//div[@class='col-md-8 col-sm-8 ng-binding']")
        values_text = [v.get_attribute('innerHTML').strip().replace(':', '') for v in values]
        print(i+1, values_text)

        for i, l in enumerate(expected_labels):
            facility[l] = values_text[i]
        profiles.append(facility)

    profiles_df = pd.DataFrame(profiles)
    profiles_df.to_csv(FACILITY_PROFILES_FILENAME)

def combine_csvs():
    # Create a new Excel workbook
    # workbook = xlsxwriter.Workbook('nv-examiners.xlsx')
    # Create Excel writer object
    # writer = pd.ExcelWriter('nv-examiners.xlsx', engine='xlsxwriter')
    writer = pd.ExcelWriter('nv-facilities.xlsx', engine='xlsxwriter')

    # Read CSV files into dataframes
    # df1 = pd.read_csv('nv-examiners.csv')
    # df2 = pd.read_csv('nv-examiner-licenses.csv')
    # df3 = pd.read_csv('nv-examiner-notices.csv')
    # df4 = pd.read_csv('nv-examiner-workplaces.csv')
    df1 = pd.read_csv(FACILITIES_FILENAME)
    df2 = pd.read_csv(FACILITY_PROFILES_FILENAME)

    # Write dataframes to separate sheets
    # df1.to_excel(writer, sheet_name='examiners', index=False)
    # df2.to_excel(writer, sheet_name='licenses', index=False)
    # df3.to_excel(writer, sheet_name='notices', index=False)
    # df4.to_excel(writer, sheet_name='workplaces', index=False)
    df1.to_excel(writer, sheet_name='facilities', index=False)
    df2.to_excel(writer, sheet_name='facility-profile', index=False)

    # Save Excel file
    writer.close()

if __name__ == '__main__':
    # os.system('clear')
    # Start webdriver
    # driver = init_driver(headless=True)

    # examiners_url = 'https://nsbvme.us.thentiacloud.net/webs/nsbvme/register/#/search/all'
    # facilities_url = 'https://nsbvme.us.thentiacloud.net/webs/nsbvme/register/#/search-facility/all'
    # load_search_results(driver, facilities_url, 'nv-facilities.csv')

    # load_examiner_profiles(driver)
    # load_facility_profiles(driver)
    
    combine_csvs()

    # Close webdriver
    # driver.quit()
    print('Done')
