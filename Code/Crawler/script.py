import time
from unittest import skip
import warnings
import orjson
from selenium.webdriver import ActionChains
from selenium.webdriver.common.keys import Keys
from pathlib import Path
from selenium.webdriver.common.by import By
import os
import sys
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import undetected_chromedriver as uc
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.common.exceptions import JavascriptException
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException, ElementClickInterceptedException
import re
import time
import sys

video_info_details = {}
companion_ads = []
engagement_ads = []
infeed_ads = []

latencyInMilliseconds = 1
downloadLimitMbps = 13.5
uploadLimitMbps = 100

TIME_TO_SLEEP = float(2 / downloadLimitMbps)

# chrome_options.add_argument("--headless")
# chrome_options.headless = False
error_list = []
auto_play_toggle = False

VIDEO_PROCESSING_TIMEOUT = 20 * 60


def handle_initial_cookie_consent(driver):
    """
    Waits for and clicks the YouTube cookie consent button if it appears.
    This is a robust method using an explicit wait and a reliable selector.

    Args:
        driver: The Selenium WebDriver instance.
    
    Returns:
        True if the button was clicked, False otherwise.
    """
    try:
        # This is the most reliable selector. It looks for a button with a specific
        # accessibility label that YouTube uses for the "Accept all" button.
        # It's independent of the page's structure and language.
        accept_button_xpath = "//button[@aria-label='Accept the use of cookies and other data for the purposes described']"
        
        # We will wait up to 10 seconds for the button to be present and clickable.
        wait = WebDriverWait(driver, 10)
        
        accept_button = wait.until(
            EC.element_to_be_clickable((By.XPATH, accept_button_xpath))
        )
        
        # If the button is found, click it.
        accept_button.click()
        print("✅ Successfully accepted cookie consent.")
        return True

    except TimeoutException:
        # This is the expected exception if the dialog does not appear.
        # It means cookies are likely already accepted or not required for the session/region.
        print("ℹ️ Cookie consent dialog not found or did not appear within 10 seconds. Continuing...")
        return False
    except Exception as e:
        # Catch any other unexpected errors during the click.
        print(f"❌ An unexpected error occurred while handling cookie consent: {e}")
        
        return False


def safe_play_video_with_tooltip_check(driver):
    """
    Plays the video by clicking the main play button if an ad is showing
    and the video is currently paused.
    """
    try:
        # Check if an ad is showing by looking for the ad container
        ad_is_showing = driver.execute_script(
            "return document.getElementsByClassName('ad-showing').length > 0;"
        )

        if ad_is_showing:
            # print("INFO: Ad detected.")
            try:
                # Wait for the play button to be present and find it
                play_button = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "button.ytp-play-button"))
                )

                # Check the tooltip to see if the video is paused
                if play_button.get_attribute("data-title-no-tooltip") == "Play":
                    print("✅ Ad is showing and main video is paused. Clicking play button.")
                    play_button.click()
                else:
                    pass
                    # This would mean the ad or video is already playing
                    # print("INFO: Ad is present, but video is not paused. No action taken.")

            except (NoSuchElementException, TimeoutException):
                print("❌ Could not find the play button while an ad was showing.")
        else:
            # This part of the logic can be expanded to handle non-ad scenarios
            # For now, we'll just report that no ad is present
            print("INFO: No ad is currently showing.")

    except Exception as e:
        print(f"An error occurred: {e}")

def get_ad_center_details_from_popup(driver, ad_center_button) -> dict:
    """
    A single, robust function to click a button, open the 'My Ad Center' popup,
    scrape details from the iframe, and safely close it.
    """
    details = {
        "advertiser_name": "N/A",
        "advertiser_location": "N/A",
        "topic": "N/A",
        "is_verified": False,
    }
    wait = WebDriverWait(driver, 5)

    try:
        # Pause video to prevent interference
        driver.execute_script("document.getElementById('movie_player').pause()")
        
        # Click the button that opens the ad center
        ad_center_button.click()

        # Wait for and switch to the iframe
        wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, "iframe")))
        print("    -> Switched to 'My Ad Center' iframe.")

        # Wait for content inside the iframe to be visible
        heading_xpath = "//div[@role='heading' and contains(text(), 'My Ad Cent')]"
        wait.until(EC.visibility_of_element_located((By.XPATH, heading_xpath)))
        print("    -> Popup is visible. Scraping details...")

        # Scrape data safely
        try:
            adv_name_xpath = "//div[text()='Advertiser']/following-sibling::div"
            raw_text = driver.find_element(By.XPATH, adv_name_xpath).text
            details["advertiser_name"] = raw_text.replace("Paid for by", "").strip()
        except NoSuchElementException:
            pass
        try:
            location_xpath = "//div[text()='Location']/following-sibling::div"
            details["advertiser_location"] = driver.find_element(By.XPATH, location_xpath).text
        except NoSuchElementException:
            pass
        try:
            topic_xpath = "//div[text()='Topic']/following-sibling::div[1]"
            details["topic"] = driver.find_element(By.XPATH, topic_xpath).text
        except NoSuchElementException:
            pass
        try:
            verified_xpath = "//div[contains(text(), 'Advertiser identity verified by Google')]"
            driver.find_element(By.XPATH, verified_xpath)
            details["is_verified"] = True
        except NoSuchElementException:
            pass
            
        print(f"    -> Scraped: {details}")

    except (TimeoutException, ElementClickInterceptedException, StaleElementReferenceException) as e:
        print(f"    -> ❌ Could not open or process 'My Ad Center' popup: {e.__class__.__name__}")
        driver.save_screenshot(f'debug_ad_center_error_{int(time.time())}.png')
    except Exception as e:
        print(f"    -> ❌ An unexpected error occurred in the ad center iframe: {e}")
    finally:
        # CRITICAL: Always switch back and clean up
        driver.switch_to.default_content()
        driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        print("    -> Switched back to main content and closed popup.")
        # Resume video
        driver.execute_script("document.getElementById('movie_player').play()")
    return details


def get_player_state(driver) -> int | None:
    """
    Gets the current state of the YouTube video player.

    Returns:
        An integer representing the player state, or None if it can't be determined.
        -1: unstarted, 0: ended, 1: playing, 2: paused, 3: buffering, 5: cued
    """
    try:
        # This JavaScript command accesses the API of the player element
    
        player_state = driver.execute_script(
        "return document.getElementById('movie_player').getPlayerState()"
    )
        return player_state
    except JavascriptException:
        print("⚠️ Could not get player state. The player might not be ready.")
        return None

def safe_play_video(driver):
    """
    Plays the video only if it is not already playing.
    Handles paused, ended, and unstarted states.
    """
    current_state = get_player_state(driver)
    
    # We play if the video is paused (2), has ended (0), is unstarted (-1), or is cued (5)
    # We do nothing if it's already playing (1) or buffering (3)
    ad_playing = driver.execute_script(
                "return document.getElementsByClassName('ad-showing').length"
            )
    
    if ad_playing:
            safe_play_video_with_tooltip_check(driver)
    if current_state in [2, -1]:
        try:
            driver.execute_script("document.getElementById('movie_player').playVideo()")
            print("✅ Sent 'play' command.")
        except JavascriptException as e:
            print(f"❌ Could not send 'play' command: {e}")
    elif current_state == 1:
        # print("ℹ️ Video is already playing. No action taken.")
        pass
    elif current_state == 3:
         print("ℹ️ Video is buffering. No action taken.")
    
    else:
        print(f"ℹ️ Video is in an unhandled state ({current_state}). No action taken.")


def safe_pause_video(driver):
    """
    Pauses the video only if it is currently playing.
    """
    current_state = get_player_state(driver)
    
    # We only need to pause if the video is actively playing (1)
    if current_state == 1:
        try:
            driver.execute_script("document.getElementById('movie_player').pauseVideo()")
            print("✅ Sent 'pause' command.")
        except JavascriptException as e:
            print(f"❌ Could not send 'pause' command: {e}")
    else:
        print("ℹ️ Video is not currently playing. No action taken to pause.")


def to_seconds(timestr):
    """Convert a time string to seconds.
    timestr: string in the form 'minute:second'
    returns: float number of seconds
    """
    seconds = 0
    for part in timestr.split(":"):
        seconds = seconds * 60 + int(part, 10)
    return seconds


def enable_stats_for_nerds(driver):
    """
    Robustly finds and clicks the 'Stats for nerds' option in the video player's context menu.

    This version uses reliable text-based selectors and a retry loop that re-opens the
    context menu on each attempt, making it resilient to UI timing issues.

    Args:
        driver: The Selenium WebDriver instance.

    Returns:
        True if 'Stats for nerds' was successfully enabled, False otherwise.
    """
    print("Attempting to enable 'Stats for nerds'...")
    try:
        movie_player = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "movie_player"))
        )
    except TimeoutException:
        print("Critical Error: The video player element could not be found.")
        return False

    # Retry up to 5 times
    for attempt in range(5):
        try:

            ActionChains(driver).context_click(movie_player).perform()
            print(f"[Attempt {attempt + 1}] Context menu opened.")
            stats_for_nerds_xpath = "//div[contains(@class, 'ytp-menuitem-label') and contains(text(), 'Stats for nerds')]"
            stats_for_nerds_button = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.XPATH, stats_for_nerds_xpath))
            )
            stats_for_nerds_button.click()
            
            WebDriverWait(driver, 2).until(
                EC.visibility_of_element_located((By.CLASS_NAME, "html5-video-info-panel"))
            )

            print("✅ Successfully enabled 'Stats for nerds' and verified panel visibility.")
            return True

        except (TimeoutException, ElementClickInterceptedException) as e:
            print(f"⚠️ Attempt {attempt + 1} failed: Could not click 'Stats for nerds'. Retrying... Error: {e.__class__.__name__}")
            try:
                movie_player.click()
            except:
                pass 
            time.sleep(0.2) 

    print("Failed to enable 'Stats for nerds' after multiple attempts.")
    return False

def pauseVideo(driver):
    player_state = driver.execute_script(
        "return document.getElementById('movie_player').getPlayerState()"
    )
    if player_state == 1:
        driver.execute_script(
            "document.getElementsByClassName('ytp-large-play-button ytp-button')[0].click()"
        )
        print("Video Paused")
    else:
        print("Video is already paused")

def start_playing_video(driver):
    player_state = driver.execute_script(
        "return document.getElementById('movie_player').getPlayerState()"
    )

    print(driver.execute_script(
        "return document.getElementById('movie_player')"
    ))
    print("Player State: ", player_state)
    if player_state == 5:
        driver.execute_script(
            "document.getElementsByClassName('ytp-large-play-button ytp-button')[0].click()"
        )

    if player_state == 1:
        return

def play_video_if_not_playing(driver):

    player_state = driver.execute_script(
        "return document.getElementById('movie_player').getPlayerState()"
    )
    if player_state == 0:
        return

    if player_state == -1:
        driver.execute_script(
            "document.getElementsByClassName('video-stream html5-main-video')[0].play()"
        )
        
    if player_state != 1:
        driver.execute_script(
            "document.getElementsByClassName('video-stream html5-main-video')[0].play()"
        )


def get_ad_info(driver, movie_id, video_info_details):

    print("Getting Ad Info")


    
    ad_id = driver.execute_script(
        'return document.getElementsByClassName("html5-video-info-panel-content")[0].children[0].children[1].textContent.replace(" ","").split("/")[0]'
    )


    while str(ad_id) == str(movie_id):
        ad_id = driver.execute_script(
            'return document.getElementsByClassName("html5-video-info-panel-content")[0].children[0].children[1].textContent.replace(" ","").split("/")[0]'
        )

    if ad_id in video_info_details.keys():
        return ad_id, None, None, None ,None ,None, None, None
        # return ad_id, int(skippable_add), skip_duration, advertiser_name, advertiser_location, is_verified


    
    try:
        skippable_add = driver.find_element(By.XPATH, "//div[contains(@class, 'ytp-skip-ad')]")
        skippable_add = True
    except NoSuchElementException:
        skippable_add = False

    try:
        duration_elem = driver.find_element(By.XPATH, "//span[contains(@class, 'ytp-time-duration')]")
        skip_duration = duration_elem.text
    
    except NoSuchElementException:
        skip_duration = -2  # Error occured, Could not get Skip Duration

    print("All good so far")
    print("Ad ID: ", ad_id, " Skippable: ", skippable_add, " Duration: ", skip_duration)
    try:
        advertiser_name = ""
        advertiser_location = ""
        topic = ""
        is_verified = None
        ad_transparency_link = None

        wait = WebDriverWait(driver, 10)
  
        button_locator = (By.CSS_SELECTOR, ".ytp-ad-player-overlay-layout .ytp-ad-info-hover-text-button button")

        attempts = 0
        max_attempts = 5

        while attempts < max_attempts:
            try:
                ad_center_button = wait.until(EC.element_to_be_clickable(button_locator))
                print("Button is clickable. Performing ActionChains click...")
                ActionChains(driver).move_to_element(ad_center_button).click().perform()
                
                print("Click action performed. Now verifying iframe...")
                iframe_locator = (By.ID, "iframe")
                wait.until(EC.frame_to_be_available_and_switch_to_it(iframe_locator))
                
                print("Switched to iframe successfully. Click was successful!")
                break # Exit the loop on success

            except StaleElementReferenceException:
                attempts += 1
                print(f"⚠️ Encountered a stale element. Retrying... (Attempt {attempts}/{max_attempts})")
                time.sleep(0.5) 
            except TimeoutException:
                print("Timed out waiting for button to be clickable OR for the iframe to appear.")
                driver.save_screenshot('debug_click_timeout.png')
                print("Saved screenshot to debug_click_timeout.png. The click likely failed to open the iframe.")
                break 
        else:
            raise Exception("Failed to click the ad center button after multiple attempts.")
        

        try:
            # 3. NOW, INSIDE THE IFRAME, wait for the popup content
            print("Waiting for the 'My Ad Centre' popup header (video)...")
            popup_header_locator = (By.XPATH, "//div[@role='heading' and contains(text(), 'My Ad Cent')]")
            wait.until(EC.visibility_of_element_located(popup_header_locator))
            print("Popup is visible. Proceeding to scrape.")

            # 4. SCRAPE DATA FROM WITHIN THE IFRAME
            try:
                advertiser_locator = (By.XPATH, "//div[text()='Advertiser']/following-sibling::div")
                advertiser_element = wait.until(EC.visibility_of_element_located(advertiser_locator))
                advertiser_raw_text = advertiser_element.text
                advertiser_name = advertiser_raw_text.replace('Paid for by ', '').strip()
            except NoSuchElementException:
                advertiser_name = "Not found"

            try:
                location_locator = (By.XPATH, "//div[text()='Location']/following-sibling::div")
                location_element = driver.find_element(*location_locator)
                advertiser_location = location_element.text.strip()
            except NoSuchElementException:
                advertiser_location = "Not found"

            try:
                verified_locator = (By.XPATH, "//div[contains(text(), 'Advertiser identity verified by Google')]")
                is_verified = len(driver.find_elements(*verified_locator)) > 0
            except NoSuchElementException:
                is_verified = None
            
            try:
                topic_xpath = "//div[text()='Topic']/following-sibling::div[1]"
                topic = driver.find_element(By.XPATH, topic_xpath).text
            except NoSuchElementException:
                pass
            xpath = "//a[contains(@href, 'adstransparency.google.com') and contains(text(), 'See more ads')]"

            try:
                ad_transparency_element = driver.find_element(By.XPATH, xpath)
                ad_transparency_link = ad_transparency_element.get_attribute("href")
            except Exception as e:
                ad_transparency_link = None

                print("Could not find the link:", e)

            
            
            print(f"Scraped Data: Name='{advertiser_name}', Location='{advertiser_location}', Verified={is_verified}, Topic='{topic}', Transparency Link: '{ad_transparency_link}'")

        except (TimeoutException, NoSuchElementException) as e:
            print(f"Error while scraping data INSIDE the video iframe: {e}")
            advertiser_location = ""
            advertiser_name = ""
            topic = ""
            is_verified = None

            with open("debug_iframe_content.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            print("    -> Saved iframe content to debug_iframe_content.html")

            

        finally:
            # 5. VERY IMPORTANT: SWITCH BACK to the main page content
            driver.switch_to.default_content()
            print("Switched back to the main content.")

            # Now you can interact with the main page again (e.g., close the popup)
            start_playing_video(driver)
            # Sending ESC to the body is a great way to close modals
            driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)

    except TimeoutException:
        print("Timed out waiting for the 'My Ad Center' iframe to appear.")
        driver.save_screenshot('debug_timeout_screenshot.png')

    except Exception as e:
        print(f"An error occurred inside the iframe: {e}")

    
    print("Add is skippable? ",int(skippable_add))

    try:
        safe_play_video(driver)  # Ensure the video is playing before looking for the skip button
        skip_button_locator = driver.find_element(By.XPATH, "//button[contains(@class, 'ytp-skip-ad-button') and .//div[text()='Skip']]")
        wait = WebDriverWait(driver, 10)
        skip_button = wait.until(EC.element_to_be_clickable(skip_button_locator))
        # Now that Selenium knows it's clickable, click it.
        skip_button.click()
        print("✅ Ad Skipped successfully.")
        skippable_add = 1
    except:
        print("⚠️ No skip button found, or the ad is not skippable.")
        print("Trying again")
        try:
            skip_button_locator = driver.find_element(By.XPATH, "//button[contains(@class, 'ytp-skip-ad-button') and .//div[text()='Skip']]")
            wait = WebDriverWait(driver, 5)
            skip_button = wait.until(EC.element_to_be_clickable(skip_button_locator))
        except:
            print("Couldn't skip")
        

    return ad_id, int(skippable_add), skip_duration, advertiser_name, advertiser_location, is_verified, topic, ad_transparency_link

def scrape_endscreen_videos(driver):
    """
    Waits for the endscreen to appear, then scrapes all recommended videos using JavaScript
    to bypass visibility issues.
    Returns a list of dictionaries, each containing info about a video.
    """
    endscreen_videos = []
    try:
        wait = WebDriverWait(driver, 10)
        wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".html5-endscreen .ytp-videowall-still"))
        )
        print("Endscreen is visible with content. Scraping recommended videos...")

        # Find all individual video suggestion containers
        video_elements = driver.find_elements(By.CLASS_NAME, "ytp-videowall-still")

        for video_elem in video_elements:
            try:
                link = video_elem.get_attribute("href")
                
                title_element = video_elem.find_element(By.CLASS_NAME, "ytp-videowall-still-info-title")
                title = driver.execute_script("return arguments[0].textContent;", title_element).strip()

                author_element = video_elem.find_element(By.CLASS_NAME, "ytp-videowall-still-info-author")
                author_views_text = driver.execute_script("return arguments[0].textContent;", author_element).strip()

                channel_name = "N/A"
                views = "N/A"
                if '•' in author_views_text:
                    parts = author_views_text.split('•')
                    channel_name = parts[0].strip()
                    views = parts[1].strip()
                else:
                    channel_name = author_views_text.strip() if author_views_text else "N/A"

                if link and title: # Ensure we got valid data
                    endscreen_videos.append({
                        "link": link,
                        "title": title,
                        "channel": channel_name,
                        "views": views
                    })
            except NoSuchElementException:
                print("Skipping a non-video element on the endscreen.")
                continue
    
    except TimeoutException:
        print("Endscreen did not appear or had no content within the timeout period.")
    except Exception as e:
        print(f"An unexpected error occurred while scraping the endscreen: {e}")

    return endscreen_videos


def scrape_in_feed_ad(driver):
    """
    Finds and scrapes an in-feed ad, including details from the 'My Ad Center' popup.

    This function locates the 'ytd-ad-slot-renderer', scrapes its primary content,
    clicks the 'three dots' menu, switches to the resulting iframe, scrapes advertiser
    details, and then safely switches back to the main document.

    Args:
        driver: The Selenium WebDriver instance.

    Returns:
        A dictionary containing the scraped ad data, or None if no ad is found.
    """

    global infeed_ads
    global video_info_details

    ad_data = {}
    try:
        ad_container = driver.find_element(By.XPATH, "//ytd-ad-slot-renderer")
        # print("In-Feed Ad container found. Scraping details...")


        try:
            image_element = ad_container.find_element(By.XPATH, ".//ad-image-view-model//img[contains(@class, 'ytwAdImageViewModelHostImage')]")
            ad_data['image'] = image_element.get_attribute('src')
        except NoSuchElementException:
            ad_data['image'] = "Not found"

        try:
            title_element = ad_container.find_element(By.XPATH, ".//span[contains(@class, 'ytwFeedAdMetadataViewModelHostTextsStyleCompactHeadline')]")
            ad_data['title'] = title_element.text
        except NoSuchElementException:
            ad_data['title'] = "Not found"

        try:
            description_element = ad_container.find_element(By.XPATH, ".//span[contains(@class, 'ytwFeedAdMetadataViewModelHostTextsStyleCompactDescription')]")
            ad_data['description'] = description_element.text
        except NoSuchElementException:
            ad_data['description'] = "Not found"

        try:
            link_element = ad_container.find_element(By.XPATH, ".//span[contains(@class, 'ytwFeedAdMetadataViewModelHostTextsStyleCompactHeadline')]//a")
            ad_data['link'] = link_element.get_attribute('href')
        except NoSuchElementException:
            ad_data['link'] = "Not found"

        try:
            cta_button = ad_container.find_element(By.XPATH, ".//a[contains(@class, 'yt-spec-button-shape-next--call-to-action')]")
            ad_data['cta_text'] = cta_button.get_attribute('aria-label')
            ad_data['cta_link'] = cta_button.get_attribute('href')
        except NoSuchElementException:
            ad_data['cta_text'] = "Not found"
            ad_data['cta_link'] = "Not found"

            

        if ad_data['image'] not in infeed_ads:

            safe_pause_video(driver)  # Ensure the video is paused before clicking

            attempts = 5
            attempt = 0
            while attempt < attempts:
                try:
                    menu_button_xpath = "//div[contains(@class,'ytwFeedAdMetadataViewModelHostMenu')]//button[contains(@title, 'My Ad Cent')]"
                    menu_button = ad_container.find_element(By.XPATH, menu_button_xpath)
                    
                    driver.execute_script("arguments[0].click();", menu_button)
                    print("Clicked the 'My Ad Center' menu button.")
                    
                    ad_data.update(scrape_ad_center_popup(driver)) # Merge the results
                    break
                    # ad_data.update(get_ad_center_details_from_popup(driver, ad_center_button))


                except (NoSuchElementException) as e:
                    print(f"Could not click the menu button: {e}")
                    driver.save_screenshot('debug_timeout_screenshot.png')

                    ad_data.update({"advertiser_name": "", "advertiser_location": "", "topic": "", "is_verified": None, "transparency_link":""})
                    attempt+=1


        if ad_data:
            if ad_data['image'] not in infeed_ads:
                infeed_ad_object = {
                            "Img": ad_data['image'],
                            "Title": ad_data['title'],
                            "Description": ad_data['description'],
                            "Action": ad_data['cta_text'],
                            "Action Link": ad_data['cta_link'],
                            "Link": ad_data['link'],
                            "Advertiser Name": ad_data['advertiser_name'],
                            "Advertiser Location": ad_data['advertiser_location'],
                            "Verified": ad_data['is_verified'],
                            "Topic": ad_data['topic'],
                            "Transparency_link" : ad_data['transparency_link']

                        }

                infeed_ad_id = "Infeed"+str(len(infeed_ads))
                if infeed_ad_id not in video_info_details.keys():
                    video_info_details[infeed_ad_id] = infeed_ad_object

                infeed_ads.append(ad_data['image'])
                print("In-feed ad details collected.")

        safe_play_video(driver)  # Ensure the video is playing after scraping
            
        return ad_data

    except NoSuchElementException:
        # print("ℹ️ No in-feed ad found on the page.")
        return None

def scrape_ad_center_popup(driver):
    """
    Handles the logic for the 'My Ad Center' iframe popup.
    Waits for iframe, switches to it, scrapes data, and switches back.
    
    Args:
        driver: The Selenium WebDriver instance.

    Returns:
        A dictionary with advertiser_name, advertiser_location, and topic.
    """
    popup_details = {
        "advertiser_name": "Not found",
        "advertiser_location": "Not found",
        "topic": "Not found",
        "is_verified": None,
        "transparency_link":None
    }
    
    try:

        wait = WebDriverWait(driver, 10)
        wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, "iframe")))
        print("✅ Switched to 'My Ad Center' iframe.")

        popup_header_locator = (By.XPATH, "//div[@role='heading' and contains(text(), 'My Ad Cent')]")
        wait.until(EC.visibility_of_element_located(popup_header_locator))
        print("Popup is visible. Proceeding to scrape.")
        
        try:
        
            adv_name_xpath = "//div[text()='Advertiser']/following-sibling::div"
            raw_text = driver.find_element(By.XPATH, adv_name_xpath).text
            popup_details["advertiser_name"] = raw_text.replace("Paid for by", "").strip()
        except NoSuchElementException:
            pass 

        # Scrape Location
        try:
            location_xpath = "//div[text()='Location']/following-sibling::div"
            popup_details["advertiser_location"] = driver.find_element(By.XPATH, location_xpath).text
        except NoSuchElementException:
            pass

        # Scrape Topic
        try:
            topic_xpath = "//div[text()='Topic']/following-sibling::div[1]"
            popup_details["topic"] = driver.find_element(By.XPATH, topic_xpath).text
        except NoSuchElementException:
            pass

        try:
            verified_xpath = "//div[contains(text(), 'Advertiser identity verified by Google')]"
            driver.find_element(By.XPATH, verified_xpath)

            print("It's Verified!")
            popup_details["is_verified"] = True
        except NoSuchElementException:
            print("Not verified")
            popup_details["is_verified"] = None
            pass

        xpath = "//a[contains(@href, 'adstransparency.google.com') and contains(text(), 'See more ads')]"

        try:
            ad_transparency_element = driver.find_element(By.XPATH, xpath)
            ad_transparency_link = ad_transparency_element.get_attribute("href")
            print("Ad Transparency Link:", ad_transparency_link)
            popup_details['transparency_link'] = ad_transparency_link
        except Exception as e:
            popup_details['transparency_link'] = None

            print("Could not find the link:", e)


    except TimeoutException:
        print("Timed out waiting for the 'My Ad Center' iframe to appear.")
    except Exception as e:
        print(f"An error occurred inside the iframe: {e}")
    finally:
        # CRITICAL: Always switch back to the main content
        driver.switch_to.default_content()
        print("Switched back to the main page content.")
        try:
            # time.sleep(2)
            driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            pass
        except:
            pass

    return popup_details



def scrape_companion_ad(driver, movie_player, video_playing):
        
        global companion_ads
        global video_info_details

        advertiser_location = ""
        advertiser_name = ""
        is_verified = None
        topic = ""
        transparency_link = None

        try:
            companion_div = driver.find_elements(By.ID,'companion')
            if companion_div:
                companion_txt = driver.find_element(By.XPATH, "//*[@id='companion']/top-banner-image-text-icon-buttoned-layout-view-model/div[2]/div[1]/ad-avatar-lockup-view-model/div[2]/span")
                companion_txt = companion_txt.get_attribute("innerText")

                companion_img = driver.find_element(By.XPATH, "//*[@id='companion']/top-banner-image-text-icon-buttoned-layout-view-model/div[1]/ad-image-view-model/div/img")
                companion_img = companion_img.get_attribute("src")    

                companion_link = driver.find_element(By.XPATH, "//*[@id='companion']/top-banner-image-text-icon-buttoned-layout-view-model/div[2]/div[1]/ad-avatar-lockup-view-model/div[2]/div/ad-details-line-view-model/span")
                companion_link = companion_link.get_attribute("innerText")

                companion_avatar = driver.find_element(By.XPATH, "//*[@id='companion']/top-banner-image-text-icon-buttoned-layout-view-model/div[2]/div[1]/ad-avatar-lockup-view-model/div[1]/ad-avatar-view-model/yt-avatar-shape/div/div/div/img")
                companion_avatar = companion_avatar.get_attribute("src")

                try:
                    if companion_img not in companion_ads:


                        safe_pause_video(driver)  # Ensure the video is playing before clicking

                        companion_button_locator = (By.XPATH, '//*[@id="companion"]/top-banner-image-text-icon-buttoned-layout-view-model/div[2]/div[2]/button-view-model/button')
                        wait = WebDriverWait(driver, 5)
                        companion_button = wait.until(EC.element_to_be_clickable(companion_button_locator))
                        companion_button.click()

                        print("Waiting for the Ad Centre iframe...")
                        iframe_locator = (By.ID, "iframe")
                        wait.until(EC.frame_to_be_available_and_switch_to_it(iframe_locator))
                        print("Switched to iframe successfully.")



                        try:
                            # 3. NOW, INSIDE THE IFRAME, wait for the popup content
                            print("Waiting for the 'My Ad Centre' popup header...")
                            popup_header_locator = (By.XPATH, "//div[@role='heading' and contains(text(), 'My Ad Cent')]")
                            wait.until(EC.visibility_of_element_located(popup_header_locator))
                            print("Popup is visible. Proceeding to scrape.")
                            
                            try:
                                # 4. SCRAPE DATA FROM WITHIN THE IFRAME
                                advertiser_locator = (By.XPATH, "//div[text()='Advertiser']/following-sibling::div")
                                advertiser_element = wait.until(EC.visibility_of_element_located(advertiser_locator))
                                advertiser_raw_text = advertiser_element.text
                                advertiser_name = advertiser_raw_text.replace('Paid for by ', '').strip()
                            except NoSuchElementException:
                                advertiser_name = "Not found"


                            try:
                                location_locator = (By.XPATH, "//div[text()='Location']/following-sibling::div")
                                location_element = driver.find_element(*location_locator)
                                advertiser_location = location_element.text.strip()
                            except NoSuchElementException:
                                advertiser_location = "Not found"


                            try:
                                verified_locator = (By.XPATH, "//div[contains(text(), 'Advertiser identity verified by Google')]")
                                is_verified = len(driver.find_elements(*verified_locator)) > 0
                            except NoSuchElementException:
                                is_verified = None

                            try:
                                topic_xpath = "//div[text()='Topic']/following-sibling::div[1]"
                                topic = driver.find_element(By.XPATH, topic_xpath).text
                            except NoSuchElementException:
                                topic = "Not found"
                            xpath = "//a[contains(@href, 'adstransparency.google.com') and contains(text(), 'See more ads')]"
                            try:
                                ad_transparency_element = driver.find_element(By.XPATH, xpath)
                                ad_transparency_link = ad_transparency_element.get_attribute("href")
                                print("Ad Transparency Link:", ad_transparency_link)
                                transparency_link = ad_transparency_link
                            except Exception as e:
                                transparency_link = None

                                print("Could not find the link:", e)
                            
                            print(f"Scraped Data: Name='{advertiser_name}', Location='{advertiser_location}', Verified={is_verified}, Topic='{topic}', Transparency Link: {transparency_link}")

                        except (TimeoutException, NoSuchElementException) as e:
                            print(f"Error while scraping data INSIDE the iframe: {e}")
                            advertiser_location = ""
                            advertiser_name = ""
                            is_verified = None
                            topic = ""
                            transparency_link = None

                        finally:
                            # 5. VERY IMPORTANT: SWITCH BACK to the main page content
                            driver.switch_to.default_content()
                            print("Switched back to the main content.")

                            # Now you can interact with the main page again (e.g., close the popup)
                            # if video_playing != 1:
                            #     movie_player.send_keys(Keys.SPACE)

                            start_playing_video(driver)
                            # Sending ESC to the body is a great way to close modals
                            # time.sleep(2)
                            driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)


                except Exception as e:
                    # print("Companion ad specifications not found or could not be clicked. ",e)
                    advertiser_location = ""
                    advertiser_name = ""
                    is_verified = None
                    topic = ""

                    safe_play_video(driver)  # Ensure the video is playing before clicking
                    # start_playing_video(driver)


                if companion_img:
                    # print(f"Found companion ad image src: {companion_img}")
                    pass
                else:
                    print("Companion ad image tag found, but 'src' attribute is missing or empty.")
                
                companion_ad_object =  {
                    "Img": companion_img,
                    "Avatar":companion_avatar,
                    "Text": companion_txt,
                    "Link":companion_link,
                    "Advertiser Name":advertiser_name,
                    "Advertiser Location":advertiser_location,
                    "Transparency Link": transparency_link,
                    "Verified": is_verified,
                    "Topic": topic,
                    }
                if companion_img not in companion_ads:
                    companion_ads.append(companion_img)
                    print("Companion ad details collected.")

                companion_id = "Companion"+str(len(companion_ads))


                if (companion_id not in video_info_details.keys()):
                    video_info_details[companion_id] = companion_ad_object 
            
        except NoSuchElementException:
            # print("Companion ad image element not found using the specified CSS selector path within the 'companion' div.")
            pass
        except Exception as e:
            print(f"An unexpected error occurred while finding companion ad image: {e}")


def scrape_engagement_ads(driver, movie_player, video_playing):

    global engagement_ads
    global video_info_details

    try:
        engagement_ad = driver.find_element(By.XPATH, "//ytd-engagement-panel-section-list-renderer[@target-id='engagement-panel-ads']//div[@id='header']//panel-ad-header-image-lockup-view-model[@class='ytwPanelAdHeaderImageLockupViewModelHost']")

        if engagement_ad:

            try:
                engagement_ad_img = driver.find_element(By.XPATH, "//*[@id='header']/panel-ad-header-image-lockup-view-model/div/div[1]/ad-image-view-model/div/img")
                engagement_ad_img = engagement_ad_img.get_attribute("src")
            except NoSuchElementException:
                engagement_ad_img = "Not found"
            
            try:
                engagement_ad_title = driver.find_element(By.XPATH, "//*[@id='header']/panel-ad-header-image-lockup-view-model/div/div[2]/div[1]/ad-avatar-lockup-view-model/div[2]/span")
                engagement_ad_title = engagement_ad_title.get_attribute("innerText")
            except NoSuchElementException:
                engagement_ad_title = "Not found"

            try:
                engagement_ad_action = driver.find_element(By.XPATH, "//*[@id='header']/panel-ad-header-image-lockup-view-model/div/div[2]/ad-button-view-model/a/div/span")
                engagement_ad_action = engagement_ad_action.get_attribute("innerText")
            except NoSuchElementException:
                engagement_ad_action = "Not found"


            try:
                engagement_link = driver.find_element(By.XPATH, '//*[@id="header"]/panel-ad-header-image-lockup-view-model/div/div[2]/div[1]/ad-avatar-lockup-view-model/div[2]/div/ad-details-line-view-model/span')
                engagement_link = engagement_link.get_attribute("innerText")
            except NoSuchElementException:
                engagement_link = "Not found"

            dropdown_active = False

            if engagement_ad_img not in engagement_ads:

                safe_pause_video(driver)  # Ensure the video is playing before clicking

                try:
                    engagement_dropdown = driver.find_element(By.XPATH, "//*[@id='header']/panel-ad-header-image-lockup-view-model/div/div[2]/div[2]/toggle-button-view-model/button-view-model/button")
                    engagement_dropdown.click()
                    dropdown_active = True
                except NoSuchElementException:
                    pass
                    # print("Engagement dropdown button not found. Skipping...")

                card_data = []
                try:
                    # Find all card elements within the ad panel
                    all_cards_xpath = ".//ad-grid-card-text-view-model"
                    card_elements = driver.find_elements(By.XPATH, all_cards_xpath)
                    
                    if card_elements:
                        print(f"    -> Found {len(card_elements)} grid card(s).")
                        # Loop through each card found
                        for i, card in enumerate(card_elements):
                            card_info = {}
                            # Scrape headline from the current card
                            try:
                                headline_xpath = ".//span[contains(@class, 'ytwAdGridCardTextViewModelHostMetadataHeadline')]"
                                card_info['headline'] = card.find_element(By.XPATH, headline_xpath).text
                            except NoSuchElementException:
                                card_info['headline'] = "Not found"
                                
                            # Scrape all description lines and join them
                            try:
                                desc_lines_xpath = ".//div[contains(@class, 'ytwAdGridCardTextViewModelHostMetadataDescriptionInline')]/span"
                                description_elements = card.find_elements(By.XPATH, desc_lines_xpath)
                                card_info['description'] = " | ".join([desc.text for desc in description_elements])
                            except NoSuchElementException:
                                card_info['description'] = "Not found"
                                
                            # Scrape the CTA link for the current card
                            try:
                                cta_link_xpath = ".//div[contains(@class, 'ytwAdGridCardTextViewModelHostButton')]//a"
                                card_info['link'] = card.find_element(By.XPATH, cta_link_xpath).get_attribute('href')
                            except NoSuchElementException:
                                card_info['link'] = "Not found"
                                
                            card_data.append(card_info)
                    else:
                        pass
                        # print("    -> No grid cards found in this ad.")

                except NoSuchElementException:
                    print("    -> Card collection container not found.")
                
                # Add the list of cards to our main dictionary

            

                try:
                    advertiser_name = ""
                    advertiser_location = ""
                    is_verified = None
                    topic = ""
                    engagement_button_locator = None
                    transparency_link = None

    
                    attempts = 0
                    max_attempts = 5
                    while attempts < max_attempts:
                        try:
                            if not dropdown_active:
                                try:
                                    engagement_dropdown = driver.find_element(By.XPATH, "//*[@id='header']/panel-ad-header-image-lockup-view-model/div/div[2]/div[2]/toggle-button-view-model/button-view-model/button")
                                    engagement_dropdown.click()
                                    dropdown_active = True
                                except NoSuchElementException:
                                    pass


                            engagement_button_locator = (By.XPATH,"//*[@id='header']/panel-ad-header-image-lockup-view-model/div/div[2]/button-view-model/button")
                            wait = WebDriverWait(driver, 10)
                            engagement_button = wait.until(EC.element_to_be_clickable(engagement_button_locator))
                            engagement_button.click()

                            print("Waiting for the Ad Centre iframe (engagement)...")
                            iframe_locator = (By.ID, "iframe")
                            wait.until(EC.frame_to_be_available_and_switch_to_it(iframe_locator))
                            print("Switched to iframe successfully.")
                            break
                        except (StaleElementReferenceException):
                            attempts += 1
                            print(f"⚠️ Encountered an issue with the engagement button. Retrying... (Attempt {attempts}/{max_attempts})")
                            time.sleep(0.5)
                        except TimeoutException:
                            print(f"Timed out waiting for the engagement button to be clickable.(Attempt {attempts}/{max_attempts})")
                            driver.save_screenshot('debug_engagement_timeout.png')
                            print("Saved screenshot to debug_engagement_timeout.png. The click likely failed to open the iframe.")
                            attempts += 1

                    else:
                        pass

                    try:
                        # 3. NOW, INSIDE THE IFRAME, wait for the popup content
                        print("Waiting for the 'My Ad Centre' popup header...")
                        popup_header_locator = (By.XPATH, "//div[@role='heading' and contains(text(), 'My Ad Cent')]")
                        wait.until(EC.visibility_of_element_located(popup_header_locator))
                        print("Popup is visible. Proceeding to scrape.")

                        # 4. SCRAPE DATA FROM WITHIN THE IFRAME
                        try:
                            advertiser_locator = (By.XPATH, "//div[text()='Advertiser']/following-sibling::div")
                            advertiser_element = wait.until(EC.visibility_of_element_located(advertiser_locator))
                            advertiser_raw_text = advertiser_element.text
                            advertiser_name = advertiser_raw_text.replace('Paid for by ', '').strip()
                        except NoSuchElementException:
                            advertiser_name = "Not found"

                        try:
                            location_locator = (By.XPATH, "//div[text()='Location']/following-sibling::div")
                            location_element = driver.find_element(*location_locator)
                            advertiser_location = location_element.text.strip()
                        except NoSuchElementException:
                            advertiser_location = "Not found"

                        try:
                            verified_locator = (By.XPATH, "//div[contains(text(), 'Advertiser identity verified by Google')]")
                            is_verified = len(driver.find_elements(*verified_locator)) > 0
                        except NoSuchElementException:
                            is_verified = None

                        try:
                            topic_xpath = "//div[text()='Topic']/following-sibling::div[1]"
                            topic = driver.find_element(By.XPATH, topic_xpath).text
                        except NoSuchElementException:
                            topic = "Not found"

                        try:
                            ad_transparency_element = driver.find_element(By.XPATH, xpath)
                            ad_transparency_link = ad_transparency_element.get_attribute("href")
                            print("Ad Transparency Link:", ad_transparency_link)
                            transparency_link = ad_transparency_link
                        except Exception as e:
                            transparency_link = None
                        
                        print(f"Scraped Data: Name='{advertiser_name}', Location='{advertiser_location}', Verified={is_verified}, Topic='{topic}'")

                    except (TimeoutException, NoSuchElementException) as e:
                        print(f"Error while scraping data INSIDE the iframe: {e}")
                        advertiser_location = ""
                        advertiser_name = ""
                        is_verified = None
                        topic = "Not found"
                        transparency_link = None

                    finally:
                        # 5. VERY IMPORTANT: SWITCH BACK to the main page content
                        driver.switch_to.default_content()
                        print("Switched back to the main content.")

                        # Now you can interact with the main page again (e.g., close the popup)
                        safe_play_video(driver)
                        # Sending ESC to the body is a great way to close modals
                        driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)

                except Exception as e:
                    # print("Companion ad specifications not found or could not be clicked. ",e)
                    advertiser_location = ""
                    advertiser_name = ""
                    is_verified = None  
                    topic = ""     

                safe_play_video(driver)  # Ensure the video is playing before clicking      

                           

            # engagement_ad_data = scrape_ad_center_popup(driver) # Merge the results

            if engagement_ad_img not in engagement_ads:
                engagement_ads.append(engagement_ad_img)

                engagement_ad_object = {
                    "Img": engagement_ad_img,
                    "Title": engagement_ad_title,
                    "Action": engagement_ad_action,
                    "Link": engagement_link,
                    "Advertiser Name": advertiser_name,
                    "Advertiser Location": advertiser_location,
                    "Verified": is_verified,
                    "Transparency Link":transparency_link,
                    "Cards": card_data,
                    "Topic": topic,
                }

                engagement_ad_id = "Engagement"+str(len(engagement_ads))
                if engagement_ad_id not in video_info_details.keys():
                    video_info_details[engagement_ad_id] = engagement_ad_object

                print("Engagement ad details collected.")


    except NoSuchElementException:
        # print("Engagement ad not found.")
        pass

def matchCurrentID(driver,actual_url):
    movie_id = actual_url.split("=")[1]
    url = driver.current_url
    match = re.search(r"[?&]v=([^&#]+)", url)
    if match:
        video_id = match.group(1)
        if str(video_id) == str(movie_id):
            return True
        else:
            return False
    else:
        return None


def driver_code(driver, filename):


    # Get the full list of video IDs from the source file
    with open(filename, "r") as f:
        all_video_ids = f.read().splitlines()

    # Define the output directory using pathlib for robustness
    folder_name = Path(filename).stem
    new_dir = Path(f"./{folder_name}")
    new_dir.mkdir(exist_ok=True)

    # Check for already processed files to avoid re-running them
    processed_ids = set()
    if new_dir.is_dir():
        processed_ids = {file.stem for file in new_dir.glob('*.txt')}

    # Filter the main list to get only the videos that haven't been processed
    list_of_urls = [video_id for video_id in all_video_ids if video_id not in processed_ids]

    print("-" * 50)
    print(f"Found {len(all_video_ids)} total videos in '{filename}'.")
    print(f"Found {len(processed_ids)} already processed videos in '{new_dir}/'.")
    print(f"--> Starting new run with {len(list_of_urls)} remaining videos. <--")
    print("-" * 50)



    for index, url in enumerate(list_of_urls):
        url = "https://www.youtube.com/watch?v=" + str(url)
        global error_list
        global auto_play_toggle
        error_list = []
        all_overlay_links = []
        unique_add_count = 0

        start_time = time.time()

        global video_info_details, companion_ads, engagement_ads, infeed_ads 

        video_info_details = {}
        companion_ads = []
        engagement_ads = []
        infeed_ads = []

        previous_ad_id = url.split("=")[1]
        movie_id = url.split("=")[1]

        print("Processing Video: ", url)    
        # time.sleep(2)
        driver.get(url)

        time.sleep(2)
        movie_player = driver.find_element(By.ID,'movie_player')
        video_playing = driver.execute_script(
                "return document.getElementById('movie_player').getPlayerState()"
            )
        
        safe_pause_video(driver)  # Ensure the video is playing before clicking
        
        # if video_playing == 1:
        #     print("Video is already playing, pausing it to start fresh.")
        #     movie_player.send_keys(Keys.SPACE)
        #     time.sleep(1)


        # Turning off Autoplay
        if not auto_play_toggle:
            print("Turning off Autoplay")
            try:
                driver.execute_script(
                    "document.getElementsByClassName('ytp-autonav-toggle-button-container')[0].click()"
                )
                auto_play_toggle = True
            except:
                pass


        try:
            # Enable Stats
            enabled = enable_stats_for_nerds(driver)

            if not enabled:
                print("Error occured while collecting data! Moving to next video!")
                print("Video: ", url)
                with open("faultyVideos.txt", "a") as f:
                    to_write = str(url) + "\n"
                    f.write(to_write)
                continue

            safe_play_video(driver)  # Ensure the video is playing before clicking

            # if video_playing != 1:
            #     movie_player.send_keys(Keys.
            # )
            #     print("Video has now started playing")
            # else:
            #     print("Video is already playing")

            video_duration_in_seconds = driver.execute_script(
                'return document.getElementById("movie_player").getDuration()'
            )

            Path(new_dir).mkdir(parents=False, exist_ok=True)

            video_playing = driver.execute_script(
                "return document.getElementById('movie_player').getPlayerState()"
            )
            

            ad_playing = driver.execute_script(
                "return document.getElementsByClassName('ad-showing').length"
            )

            if ad_playing:
                ad_id, skippable, skip_duration, advertiser_name, advertiser_location, is_verified, topic, transparency_link = get_ad_info(driver, movie_id, video_info_details)
                if ad_id not in video_info_details.keys():
                    if ad_id != "empty_video ":
                        unique_add_count += 1
                        video_info_details[ad_id] = {
                            "Count": 1,
                            "Skippable": skippable,
                            "SkipDuration": skip_duration,
                            "Advertiser Name": advertiser_name,
                            "Advertiser Location": advertiser_location,
                            "Transparency Link": transparency_link,
                            "Verified": is_verified,
                            "Topic": topic
                        }
                        previous_ad_id = ad_id
                        print("Advertisement " + str(unique_add_count) + " Data collected.")

            while True:
                # time.sleep(0.5)
                play_video_if_not_playing(driver)
                safe_play_video(driver)
                video_playing = driver.execute_script(
                    "return document.getElementById('movie_player').getPlayerState()"
                )

                scrape_companion_ad(driver, movie_player, video_playing)
                scrape_in_feed_ad(driver)
                scrape_engagement_ads(driver, movie_player, video_playing)

                ### OVERLAY LINKS
                try:
                    overlay_links = driver.find_elements(By.XPATH, "//a[contains(@class, 'ytp-ce-covering-overlay') and @href]")
                    hrefs = [link.get_attribute("href") for link in overlay_links]
                    all_overlay_links.extend(hrefs)
                    all_overlay_links = list(set(all_overlay_links))
                except:
                    pass
                ### OVERLAY LINKS

                ad_playing = driver.execute_script(
                    "return document.getElementsByClassName('ad-showing').length"
                )
                # time.sleep(0.5)

                video_playing = driver.execute_script(
                    "return document.getElementById('movie_player').getPlayerState()"
                )

                if ad_playing:
                    # Ad is being played

                    ad_id, skippable, skip_duration,advertiser_name, advertiser_location, is_verified, topic, transparency_link = get_ad_info(
                        driver, movie_id, video_info_details
                    )
                    if ad_id != previous_ad_id:
                        print("Ad Playing")
                        if ad_id not in video_info_details.keys():
                            unique_add_count += 1
                            video_info_details[ad_id] = {
                                "Count": 1,
                                "Skippable": skippable,
                                "SkipDuration": skip_duration,
                                "Advertiser Name": advertiser_name,
                                "Advertiser Location": advertiser_location,
                                "Transparency Link": transparency_link,                            
                                "Verified": is_verified,
                                "Topic": topic
                            }
                            print(
                                "Advertisement "
                                + str(unique_add_count)
                                + " Data collected."
                            )
                        else:
                            print("Check: ", ad_id)
                            print("Check player state: ",get_player_state(driver))
                            current_value = video_info_details[ad_id]["Count"]
                            video_info_details[ad_id]["Count"] = current_value + 1
                            print("Count of existing add increased!")
                   


                elif (video_playing == 0) or not matchCurrentID(driver, url):
                    # Video has ended
                    file_dir = new_dir / f"{movie_id}.txt" # CORRECTED LINE
                    endscreen_data = scrape_endscreen_videos(driver)

                    video_info_details["Main_Video"] = {
                        "Url": url,
                        "Total Duration": video_duration_in_seconds,
                        "UniqueAds": unique_add_count,
                        "OverlayLinks": all_overlay_links,
                        "Endscreen_Recommendations": endscreen_data
                    }

                    with open(file_dir, "wb+") as f:
                        f.write(orjson.dumps(video_info_details))
                    video_info_details = {}
                    unique_add_count = 0
                    print("Video Finished and details written to files!")
                    break
                else:
                    # Video is playing normally
                    previous_ad_id = url.split("=")[1]

                elapsed_time = time.time() - start_time

                # print("Elapsed Time: ", elapsed_time, " seconds", "Start Time: ", start_time)
                if elapsed_time > VIDEO_PROCESSING_TIMEOUT:

                    file_dir = new_dir / f"{movie_id}.txt" # CORRECTED LINE
                    endscreen_data = scrape_endscreen_videos(driver)

                    video_info_details["Main_Video"] = {
                        "Url": url,
                        "Total Duration": video_duration_in_seconds,
                        "UniqueAds": unique_add_count,
                        "OverlayLinks": all_overlay_links,
                        "Endscreen_Recommendations": endscreen_data
                    }

                    with open(file_dir, "wb+") as f:
                        f.write(orjson.dumps(video_info_details))
                    video_info_details = {}
                    unique_add_count = 0
                    print("Video Finished and details written to files!")
                    break
               
        except Exception as e:
            print(e)
            print("Error occured while collecting data! Moving to next video!")
            print("Video: ", url)
            with open("faultyVideos.txt", "a") as f:
                to_write = str(url) + "\n"
                f.write(to_write)
            continue







filename = sys.argv[1]
profile_dir = sys.argv[2]

warnings.filterwarnings("ignore", category=DeprecationWarning)
chrome_options = uc.ChromeOptions()
chrome_options.add_argument("--mute-audio")
chrome_options.add_argument(f"--user-data-dir={profile_dir}")

driver = uc.Chrome(options=chrome_options,version_main=138 ,multi_procs=True)

# 1. Navigate to YouTube first to handle the site-wide consent
print("Navigating to YouTube.com to handle initial consent...")
driver.get("https://www.youtube.com/")

handle_initial_cookie_consent(driver)

time.sleep(5)  # Wait for the page to load properly
driver_code(driver, filename)
driver.quit()
