#
#
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.credentials import Credentials
import json
import os.path
import argparse
import logging
from os import listdir
from os.path import isfile, join
import rawpy
import imageio
import sys
import shutil
from PIL import Image

def auth(scopes):
        flow = InstalledAppFlow.from_client_secrets_file(
            'client_id.json',
            scopes = scopes
        )

        cridentials = flow.run_local_server(host='localhost',
            power = 8081,
            authorization_prompt_message = "",
            success_message='the auth flow is completel you may close this window.',
            open_browser=True)

        return cridentials



def get_authorized_session():
    scopes=['https://www.googleapis.com/auth/photoslibrary',
            'https://www.googleapis.com/auth/photoslibrary.sharing']
    
    cred = None

    cred = auth(scopes)

    session = AuthorizedSession(cred)

    return session

def getAlbums(session, appCreatedOnly=False):
    params = {
        'excludeNonAppCreatedData': appCreatedOnly
    }

    while True:
        albums = session.get('https://photoslibrary.googleapis.com/v1/albums', params=params).json()

        if 'albums' in albums:
            for a in albums['albums']:
                yield a

            if 'nextPageToken' in albums:
                params["pageToken"] = albums["nextPageToken"]
            else:
                return
        else:
            return

def create_or_retrieve_album(session, album_title):
    for a in getAlbums(session, False):
        if a["title"].lower() == album_title.lower():
            album_id = a["id"]
            return album_id;
    
    create_album_body = json.dumps({"album":{"title": album_title}})

    resp = session.post('https://photoslibrary.googleapis.com/v1/albums', create_album_body).json()

    if "id" in resp:
        return resp['id']
    else:
        return None

def upload_photos(session, photo_file_list, album_name):
    album_id = create_or_retrieve_album(session, album_name) if album_name else None

    if album_name and not album_id:
        return
    
    session.headers["Content-type"] = "application/octet-stream"
    session.headers["X-Goog-Upload-Protocol"] = "raw"

    for photo_file_name in photo_file_list:
        try:
            photo_file =open(photo_file_name, mode='rb')
            photo_bytes = photo_file.read()
        except OSError as err:
            print(err)

        session.headers["X-Goog-Upload-File-Name"] = os.path.basename(photo_file_name)

        upload_token = session.post('https://photoslibrary.googleapis.com/v1/uploads', photo_bytes)

        if (upload_token.status_code == 200) and (upload_token.content):

            create_body = json.dumps({"albumId":album_id, "newMediaItems":[{"description":"","simpleMediaItem":{"uploadToken":upload_token.content.decode()}}]}, indent=4)

            resp = session.post('https://photoslibrary.googleapis.com/v1/mediaItems:batchCreate', create_body).json()

            #print("Server response: {}".format(resp))

            if "newMediaItemResults" in resp:
                status = resp["newMediaItemResults"][0]["status"]
                if status.get("code") and (status.get("code") > 0):
                    print("Could not add \'{0}\' to library -- {1}".format(os.path.basename(photo_file_name), status["message"]))
                else:
                    print("Added \'{}\' to library and album \'{}\' ".format(os.path.basename(photo_file_name), album_name))
            else:
                logging.error("Could not add \'{0}\' to library. Server Response -- {1}".format(os.path.basename(photo_file_name), resp))

        else:
            print("Could not upload \'{0}\'. Server Response - {1}".format(os.path.basename(photo_file_name), upload_token))

    try:
        del(session.headers["Content-type"])
        del(session.headers["X-Goog-Upload-Protocol"])
        del(session.headers["X-Goog-Upload-File-Name"])
    except KeyError:
        pass

def parse_path(args):
    if len(args) == 1 or len(args[1]) == 0:
        print("Please enter a file path")
        return ""
    
    if os.path.exists(args[0]) == False:
        print("Path does not exist")
        return ""

    return args[1]

def main():
    session = get_authorized_session()

    path = parse_path(sys.argv)

    if path == "":
        return



    for root, dirs, files in os.walk(path):
        for sd in dirs:
            onlyfiles = []

            d = root + '/' + sd

            dtemp = d + '/temp/'

            if os.path.exists(dtemp) == False:
                os.mkdir(dtemp)
            else:
                for f in os.listdir(dtemp):
                    os.remove(os.path.join(dtemp, f))

            for path in os.listdir(d):
                full_path = os.path.join(d, path)
                if os.path.isfile(full_path):
                    fileName = os.path.splitext(os.path.basename(full_path))[0]
                    
                    impath = dtemp + fileName + '.jpg'

                    filename, file_extension = os.path.splitext(full_path)

                    if file_extension.lower() == ".jpg":
                        print("image is already a jpg.")
                        shutil.copy(full_path, impath)
                        onlyfiles.append(impath)
                    elif file_extension.lower() == ".png":
                        print("image is a png. converting to jpg")
                        im1 = Image.Open(full_path)
                        im1.save(impath)
                        onlyfiles.append(impath)
                    else:
                        print('Converting ' + fileName + " to " + impath) 
                        try:
                            with rawpy.imread(full_path) as raw:
                                rgb = raw.postprocess()
                            
                            imageio.imsave(impath, rgb)

                            onlyfiles.append(impath)
                        except:
                            e = sys.exc_info()[0]
                            print(e)


            upload_photos(session, onlyfiles, os.path.basename(d).replace(':', '/'))

            try:
                os.remove(dtemp)
            except:
                continue

if __name__ == '__main__':
    main()