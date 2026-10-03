from playwright.sync_api import sync_playwright, TimeoutError
from pathlib import Path
from PIL import Image
import time


def generate_images(prompts, output_folder, progress_callback=None):
    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)

    generation_timeout = 180
    download_timeout = 180

    # Keep track of prompts that failed
    failed_prompts = []

    with sync_playwright() as p:

        # IMPORTANT:
        # Preserve Chrome's own download behavior when attaching
        # to the user's normal Chrome browser.
        browser = p.chromium.connect_over_cdp(
            "chrome",
            no_defaults=True
        )

        context = browser.contexts[0]

        flow_page = next(
            page for page in context.pages
            if "flow.google.com" in page.url
        )

        print("Connected to Flow!")

        # --------------------------------------------------------
        # CHROME NATIVE DOWNLOAD EVENTS
        # --------------------------------------------------------

        browser_cdp = browser.new_browser_cdp_session()

        browser_cdp.send(
            "Browser.setDownloadBehavior",
            {
                "behavior": "default",
                "eventsEnabled": True
            }
        )

        download_state = {
            "guid": None,
            "suggested_filename": None,
            "file_path": None,
            "state": None
        }

        def download_will_begin(params):

            if download_state["guid"] is None:

                download_state["guid"] = params.get("guid")

                download_state["suggested_filename"] = (
                    params.get("suggestedFilename")
                )

                print(
                    "Chrome download started: "
                    f"{download_state['suggested_filename']}"
                )

        def download_progress(params):

            if params.get("guid") == download_state["guid"]:

                download_state["state"] = (
                    params.get("state")
                )

                if params.get("filePath"):

                    download_state["file_path"] = (
                        params.get("filePath")
                    )

        browser_cdp.on(
            "Browser.downloadWillBegin",
            download_will_begin
        )

        browser_cdp.on(
            "Browser.downloadProgress",
            download_progress
        )

        prompt_box = flow_page.locator(
            "[contenteditable='true']"
        ).first

        total = len(prompts)

        for number, item in enumerate(prompts, start=1):

            timestamp = item["timestamp"]
            prompt = item["prompt"]

            # Tell Streamlit which prompt is currently running
            if progress_callback:

                progress_callback(
                    number - 1,
                    total,
                    timestamp,
                    "Generating..."
                )

            print()
            print("=" * 50)
            print(f"PROCESSING {timestamp}")
            print("=" * 50)

            # ------------------------------------------------
            # ENTER PROMPT
            # ------------------------------------------------
            # Flow may temporarily make the prompt editor
            # unavailable after the previous generation.
            # Retry for up to 60 seconds instead of stopping
            # the entire automation.
            # ------------------------------------------------

            prompt_entered = False
            prompt_entry_start = time.time()

            while (
                time.time() - prompt_entry_start
                < 60
            ):

                try:

                    prompt_box.wait_for(
                        state="visible",
                        timeout=5000
                    )

                    prompt_box.click(
                        timeout=5000
                    )

                    prompt_box.fill(
                        prompt,
                        timeout=5000
                    )

                    prompt_entered = True

                    print("Prompt entered.")

                    break

                except TimeoutError:

                    print(
                        "Flow prompt editor is not ready yet. "
                        "Retrying..."
                    )

                    flow_page.wait_for_timeout(2000)

            # ------------------------------------------------
            # IF PROMPT COULD NOT BE ENTERED
            # ------------------------------------------------

            if not prompt_entered:

                print()
                print("!" * 50)
                print(
                    f"PROMPT ENTRY FAILED: {timestamp}"
                )
                print(
                    "Could not enter the prompt into "
                    "the Flow editor within 60 seconds."
                )
                print("Skipping to next prompt...")
                print("!" * 50)

                failed_prompts.append(
                    {
                        "timestamp": timestamp,
                        "prompt": prompt,
                        "reason": (
                            "Could not enter the prompt into "
                            "the Flow editor within 60 seconds."
                        )
                    }
                )

                if progress_callback:

                    progress_callback(
                        number,
                        total,
                        timestamp,
                        "Failed"
                    )

                continue

            # ------------------------------------------------
            # Remember images that already exist
            # ------------------------------------------------

            existing_media_ids = flow_page.locator(
                "flow-grid-tile-container img"
            ).evaluate_all(
                """
                images => images
                    .map(image =>
                        image.getAttribute('data-media-id')
                    )
                    .filter(Boolean)
                """
            )

            # ------------------------------------------------
            # Start generation
            # ------------------------------------------------

            flow_page.get_by_role(
                "button",
                name="Start generation"
            ).click()

            print("Generation started.")

            print(
                f"Waiting up to {generation_timeout} seconds..."
            )

            # ------------------------------------------------
            # WAIT FOR A NEW IMAGE
            # ------------------------------------------------

            try:

                new_image = flow_page.wait_for_function(
                    """
                    existingIds => {
                        const image = [
                            ...document.querySelectorAll(
                                'flow-grid-tile-container img'
                            )
                        ].find(
                            item =>
                                item.complete &&
                                item.naturalWidth > 0 &&
                                item.dataset.mediaId &&
                                !existingIds.includes(
                                    item.dataset.mediaId
                                )
                        );

                        return image?.dataset.mediaId || false;
                    }
                    """,
                    arg=existing_media_ids,
                    timeout=generation_timeout * 1000
                )

            except TimeoutError:

                # --------------------------------------------
                # GENERATION FAILED / TIMED OUT
                # --------------------------------------------

                print()
                print("!" * 50)
                print(f"GENERATION FAILED: {timestamp}")

                print(
                    f"No new image appeared within "
                    f"{generation_timeout} seconds."
                )

                print("Skipping to next prompt...")
                print("!" * 50)

                failed_prompts.append(
                    {
                        "timestamp": timestamp,
                        "prompt": prompt,
                        "reason": (
                            f"No image generated within "
                            f"{generation_timeout} seconds."
                        )
                    }
                )

                # Tell Streamlit this prompt failed
                if progress_callback:

                    progress_callback(
                        number,
                        total,
                        timestamp,
                        "Failed"
                    )

                # Continue with next prompt
                continue

            new_media_id = new_image.json_value()

            image_card = flow_page.locator(
                "flow-grid-tile-container"
                f":has(img[data-media-id='{new_media_id}'])"
            )

            print("New image appeared.")

            # Open image menu
            image_card.hover()

            image_card.get_by_label(
                "More options"
            ).click()

            print("Opened image menu.")

            # Select Download
            flow_page.get_by_text(
                "Download",
                exact=True
            ).click()

            print("Download menu opened.")

            # ------------------------------------------------
            # START FRESH DOWNLOAD TRACKING
            # ------------------------------------------------

            download_state["guid"] = None
            download_state["suggested_filename"] = None
            download_state["file_path"] = None
            download_state["state"] = None

            # ------------------------------------------------
            # Select 2K download
            # ------------------------------------------------

            flow_page.get_by_text(
                "2K",
                exact=True
            ).click()

            print("Flow download started.")

            # ------------------------------------------------
            # WAIT FOR CHROME'S NATIVE DOWNLOAD
            # ------------------------------------------------

            download_start = time.time()

            while True:

                if (
                    download_state["state"] == "completed"
                    and download_state["file_path"]
                ):
                    break

                if download_state["state"] == "canceled":

                    raise RuntimeError(
                        f"Flow download was canceled for "
                        f"[{timestamp}]"
                    )

                if (
                    time.time() - download_start
                    > download_timeout
                ):

                    raise TimeoutError(
                        f"Flow download did not complete "
                        f"within {download_timeout} seconds "
                        f"for [{timestamp}]"
                    )

                flow_page.wait_for_timeout(250)

            download_file = Path(
                download_state["file_path"]
            )

            print(
                f"Download completed: {download_file}"
            )

            # Make sure the file actually exists
            if not download_file.exists():

                raise RuntimeError(
                    "Chrome reported the download as completed, "
                    "but the file could not be found: "
                    f"{download_file}"
                )

            # ------------------------------------------------
            # WINDOWS-SAFE FINAL FILENAME
            # ------------------------------------------------

            safe_timestamp = timestamp.replace(
                ":",
                "."
            )

            output_file = (
                output_folder /
                f"{safe_timestamp}.jpg"
            )

            print("Converting to JPG...")

            try:

                image = Image.open(
                    download_file
                )

                print(
                    f"Original image format: {image.format}"
                )

                image = image.convert("RGB")

                image.save(
                    output_file,
                    "JPEG",
                    quality=95
                )

            finally:

                # Remove the temporary Flow download
                # from Chrome's normal Downloads folder
                # after successful processing.
                download_file.unlink(
                    missing_ok=True
                )

            print(
                f"Saved: {output_file}"
            )

            # Tell Streamlit this prompt is complete
            if progress_callback:

                progress_callback(
                    number,
                    total,
                    timestamp,
                    "Completed"
                )

            time.sleep(3)

        print()
        print("=" * 50)

        if failed_prompts:

            print(
                f"GENERATION FINISHED WITH "
                f"{len(failed_prompts)} FAILED PROMPTS"
            )

            for failed in failed_prompts:

                print(
                    f"- [{failed['timestamp']}] "
                    f"{failed['prompt']}"
                )

        else:

            print("ALL IMAGES COMPLETED!")

        print("=" * 50)

    # Return failed prompts to the frontend
    return failed_prompts