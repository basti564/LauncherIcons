import concurrent.futures
import json
import logging
import os

import requests


logging.basicConfig(level=logging.INFO)
session = requests.Session()


def merge_apps(existing_apps, new_apps):
    logging.info("Merging existing and new apps...")
    existing_packages = {app['packageName'] for app in existing_apps}
    merged_data = []
    for new_app in new_apps:
        package_name = new_app["packageName"]
        if package_name in existing_packages:
            app_data = {
                "appName": new_app.get("appName", ""),
                "packageName": package_name,
                "id": new_app.get("id", "")
            }
            merged_data.append(app_data)
        else:
            logging.info(f"MISSING:\n{{appName: {new_app.get('appName', '')}, packageName: {package_name}, id: {new_app.get('id', '')}}}")
            merged_data.append(new_app)
    return merged_data


def fetch_pico_apps(existing_apps):
    logging.info("Fetching Pico apps...")
    pico_options = {
        "url": "https://appstore-us.picovr.com/api/app/v1/section/info",
        "method": "POST",
        "params": {
            "manifest_version_code": "300800000",
            "app_language": "en",
            "size": "20",
            "device_name": "A8110",
            "page": "1",
            "section_id": "3",
        },
    }

    def fetch_apps():
        nonlocal page, has_more, app_data
        pico_options["params"]["page"] = str(page)

        response = session.request(**pico_options)
        response_data = response.json()
        new_apps = [
            dict(
                app,
                appName=app.get("name", ""),
                packageName=app.get("package_name", ""),
                id=app.get("item_id", ""),
            )
            for app in response_data["data"]["items"]
            if app.get("package_name")
        ]
        app_data.extend(new_apps)

        has_more = response_data["data"]["has_more"]
        if has_more:
            page += 1
            fetch_apps()

    page = 1
    has_more = True
    app_data = []
    fetch_apps()

    # Merge the existing and new data
    merged_data = merge_apps(existing_apps, app_data)

    # Write the updated data to the pico_apps.json file
    with open("pico_apps.json", "w") as f:
        json.dump(merged_data, f)

    logging.info("Pico apps fetched successfully.")
    return merged_data


def fetch_oculus_apps(existing_apps):
    logging.info("Fetching Oculus apps...")
    oculus_options = {
        "url": "https://oculusdb.rui2015.me/api/v1/allapps",
        "method": "GET",
    }

    response = session.request(**oculus_options)
    data = response.json()

    new_apps = [
        dict(
            app,
            appName=app.get("appName", ""),
            packageName=app.get("packageName", ""),
            id=app.get("id", ""),
        )
        for app in data
        if app.get("packageName") and "rift" not in app.get("packageName")
    ]
    app_data = merge_apps(existing_apps, new_apps)

    # Write the updated data to the oculus_apps.json file
    with open("oculus_apps.json", "w") as f:
        json.dump(app_data, f)

    logging.info("Oculus apps fetched successfully.")


def fetch_oculus_apps_with_covers(existing_apps):
    logging.info("Fetching Oculus apps...")

    section_ids = ["1888816384764129", "174868819587665"]

    landscape_folder = "oculus_landscape"
    portrait_folder = "oculus_portrait"
    square_folder = "oculus_square"

    os.makedirs(landscape_folder, exist_ok=True)
    os.makedirs(portrait_folder, exist_ok=True)
    os.makedirs(square_folder, exist_ok=True)

    new_apps = []

    with concurrent.futures.ThreadPoolExecutor() as executor:
        for section_id in section_ids:
            items_api_url = f"https://graph.oculus.com/graphql?forced_locale=en_US&doc_id=4743589559102018&access_token=OC|1076686279105243|&variables={{\"sectionId\":\"{section_id}\",\"sortOrder\":null,\"sectionItemCount\":1000}}"

            response = session.get(items_api_url)
            response_data = response.json()

            edges = response_data['data']['node']['all_items']['edges']

            for edge in edges:
                node = edge['node']
                app_details_api_url = f"https://graph.oculus.com/graphql?access_token=OC|1076686279105243|&doc_id=3828663700542720&variables={{\"applicationID\":\"{node['id']}\"}}"

                try:
                    app_details_response = session.get(app_details_api_url)
                    app_details_data = app_details_response.json()
                    latest_supported_binary = app_details_data['data']['node']['release_channels']['nodes'][0]['latest_supported_binary']

                    if latest_supported_binary is not None:
                        app_binary_info_api_url = f"https://graph.oculus.com/graphql?doc=query ($params: AppBinaryInfoArgs!) {{ app_binary_info(args: $params) {{ info {{ binary {{ ... on AndroidBinary {{ id package_name version_code asset_files {{ edges {{ node {{ ... on AssetFile {{ file_name uri size }} }} }} }} }} }} }} }} }}&variables={{\"params\":{{\"app_params\":[{{\"app_id\":\"{node['id']}\",\"version_code\":\"{latest_supported_binary['version_code']}\"}}]}}}}&access_token=OC|1317831034909742|"

                        app_binary_info_response = session.get(app_binary_info_api_url)
                        app_binary_info_data = app_binary_info_response.json()
                        package_name = app_binary_info_data['data']['app_binary_info']['info'][0]['binary']['package_name']
                        display_name = node['display_name']

                        landscape_url = node['cover_landscape_image']['uri']
                        portrait_url = node['cover_portrait_image']['uri']
                        square_url = node['cover_square_image']['uri']

                        executor.submit(download_image, landscape_url, os.path.join(landscape_folder, f"{package_name}.jpg"))
                        executor.submit(download_image, portrait_url, os.path.join(portrait_folder, f"{package_name}.jpg"))
                        executor.submit(download_image, square_url, os.path.join(square_folder, f"{package_name}.jpg"))

                        logging.info(f"Downloaded images for {package_name}")

                        new_apps.append({
                            "appName": display_name,
                            "packageName": package_name,
                            "id": node['id']
                        })

                except Exception as error:
                    logging.error(f"Error: {error}")

    merged_apps = merge_apps(existing_apps, new_apps)

    # Write the updated data to the oculus_apps.json file
    with open("oculus_apps.json", "w") as f:
        json.dump(merged_apps, f)

    logging.info("Oculus apps fetched successfully.")


def download_image(url, filename):
    with requests.get(url, stream=True) as response:
        response.raise_for_status()
        with open(filename, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)


def fetch_pico_covers(app_data):
    logging.info("Fetching Pico app covers...")
    if not os.path.exists("pico_square"):
        os.makedirs("pico_square")
    if not os.path.exists("pico_landscape"):
        os.makedirs("pico_landscape")

    urls = [
        f"https://appstore-us.picovr.com/api/app/v1/item/info?app_language=en&device_name=A8110&item_id={app['id']}&manifest_version_code=300800000"
        for app in app_data
    ]

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        square_filenames = []
        landscape_filenames = []
        futures = []
        for url in urls:
            futures.append(executor.submit(session.post, url))

        for future, app in zip(futures, app_data):
            try:
                response = future.result()
                response.raise_for_status()
                data = response.json()
                square_url = data["data"]["cover"]["square"]
                landscape_url = data["data"]["cover"]["landscape"]
                square_filename = f"pico_square/{app['packageName']}.png"
                landscape_filename = f"pico_landscape/{app['packageName']}.png"
                square_filenames.append(square_filename)
                landscape_filenames.append(landscape_filename)
                executor.submit(download_image, square_url, square_filename)
                executor.submit(download_image, landscape_url, landscape_filename)
                logging.info(f"Downloaded Covers for {app['packageName']}")
            except Exception as e:
                error_msg = f"Error: {str(e)}\n"
                with open("pico_cover_errors.log", "a") as f:
                    f.write(error_msg + "\n")
                logging.error(error_msg)
                continue

    logging.info("All Pico app covers downloaded.")


if __name__ == "__main__":
    try:
        with open("pico_apps.json") as f:
            existing_pico_apps = json.load(f)
    except FileNotFoundError:
        existing_pico_apps = []

    app_data = fetch_pico_apps(existing_pico_apps)
    fetch_pico_covers(app_data)

    try:
        with open("oculus_apps.json") as f:
            existing_oculus_apps = json.load(f)
    except FileNotFoundError:
        existing_oculus_apps = []

    fetch_oculus_apps_with_covers(existing_oculus_apps)
