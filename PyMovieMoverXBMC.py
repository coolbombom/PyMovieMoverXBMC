# -*- coding: utf-8 -*-

from xmlrpclib import ServerProxy
import urllib2, urllib, urlparse, json
import os
import glob, shutil, zipfile
import datetime, time
import re
import traceback, sys, subprocess

#YouTube quality and codecs id map.
#source: http://en.wikipedia.org/wiki/YouTube#Quality_and_codecs
YT_ENCODING = {
    #id: [extension, resoultion, video_codec, profile, video_bitrate, audio_codec, audio_bitrate]
    #Flash Video
    5: ["flv", "240p", "Sorenson H.263", "N/A", "0.25", "MP3", "64"],
    6: ["flv", "270p", "Sorenson H.263", "N/A", "0.8", "MP3", "64"],
    34: ["flv", "360p", "H.264", "Main", "0.5", "AAC", "128"],
    35: ["flv", "480p", "H.264", "Main", "0.8-1", "AAC", "128"],

    #3GP
    36: ["3gp", "240p", "MPEG-4 Visual", "Simple", "0.17", "AAC", "38"],
    13: ["3gp", "N/A", "MPEG-4 Visual", "N/A", "0.5", "AAC", "N/A"],
    17: ["3gp", "144p", "MPEG-4 Visual", "Simple", "0.05", "AAC", "24"],

    #MPEG-4
    18: ["mp4", "360p", "H.264", "Baseline", "0.5", "AAC", "96"],
    22: ["mp4", "720p", "H.264", "High", "2-2.9", "AAC", "192"],
    37: ["mp4", "1080p", "H.264", "High", "3-4.3", "AAC", "192"],
    38: ["mp4", "3072p", "H.264", "High", "3.5-5", "AAC", "192"],
    82: ["mp4", "360p", "H.264", "3D", "0.5", "AAC", "96"],
    83: ["mp4", "240p", "H.264", "3D", "0.5", "AAC", "96"],
    84: ["mp4", "720p", "H.264", "3D", "2-2.9", "AAC", "152"],
    85: ["mp4", "520p", "H.264", "3D", "2-2.9", "AAC", "152"],

    #WebM
    43: ["webm", "360p", "VP8", "N/A", "0.5", "Vorbis", "128"],
    44: ["webm", "480p", "VP8", "N/A", "1", "Vorbis", "128"],
    45: ["webm", "720p", "VP8", "N/A", "2", "Vorbis", "192"],
    46: ["webm", "1080p", "VP8", "N/A", "N/A", "Vorbis", "192"],
    100: ["webm", "360p", "VP8", "3D", "N/A", "Vorbis", "128"],
    101: ["webm", "360p", "VP8", "3D", "N/A", "Vorbis", "192"],
    102: ["webm", "720p", "VP8", "3D", "N/A", "Vorbis", "192"]
}

# The keys corresponding to the quality/codec map above.
YT_ENCODING_KEYS = (
    'extension', 'resolution', 'video_codec', 'profile', 'video_bitrate',
    'audio_codec', 'audio_bitrate'
)

home_folder = os.path.dirname(os.path.realpath(__file__))
percent_copied = "0"

def removeNonAscii(s): 
   return "".join(i for i in s if ord(i)<128)

def download_subs(imdb_id, title, output):
   log('searching for subtitles for: '+title,'info')
   subfound = False
   imdbid = imdb_id.replace('tt','')
   try:
      s = ServerProxy("http://api.opensubtitles.org/xml-rpc")
      res = s.LogIn("", "", "en", settings['config']['opensub_agent'])
   except:
      log("error connecting to opensubtitles server","error")
      res = ""
   if (("status" in res) and (res['status'] == '200 OK')):
      query = []
      for language in settings['config']['opensub_languages']:
         query.append({'sublanguageid': language, 'imdbid': imdbid})
      subtitles = s.SearchSubtitles(res['token'], query)['data']
      subtitles = filter(lambda x: x['SubBad'] == '0', subtitles) if subtitles else False
      subtitles = filter(lambda x: float(x['SubRating']) >= settings['config']['opensub_min_rating'] or float(x['SubRating']) == 0.0, subtitles)  if subtitles else False
      if subtitles:
         for language in settings['config']['opensub_languages']:
            langsubs = filter(lambda x: x['SubLanguageID'] == language, subtitles)
            if langsubs:
               subfound = True
               langsubs.sort(key=lambda x: float(x['SubRating']))
               langsubs.reverse()
               if not os.path.isfile(os.path.join(output,'sub-'+language+'.zip')):
                  log('SUB FOUND: '+langsubs[0]['MovieReleaseName']+" - "+langsubs[0]['SubRating']+" - "+langsubs[0]['SubLanguageID'],'info')
                  download(langsubs[0]['ZipDownloadLink'], os.path.join(output,'sub-'+language+'.zip'))
                  if (not os.path.isfile(os.path.join(output,os.path.splitext(title)[0]+".srt"))) and (settings['config']['opensub_auto_extract']):
                     try_except(unpack,[os.path.join(output,'sub-'+language+'.zip'), output, os.path.splitext(title)[0]+".srt",".srt"],'error occured while trying to unpack: sub-'+langsubs[0]['SubLanguageID']+'.zip')
   if not subfound:
      log("no subtitles found for: "+title,"info")

def download(remote, local=None):
   log("downloading: %s" % remote,'info')
   local = home_folder if (local==None) else local
   return try_except(urllib.urlretrieve,[remote,local],'error occured while trying to download: '+remote)

def unpack(zip_file, out_path='', out_filename='', ext_unpack=''):
   if os.path.isfile(zip_file):
      out_path = os.path.dirname(os.path.realpath(zip_file)) if ((out_path=='') or (not os.path.exists(out_path))) else out_path
      fh = open(zip_file, 'rb')
      zfile = zipfile.ZipFile(fh)
      for name in zfile.namelist():
         if ((name.endswith(ext_unpack)) or (ext_unpack=='')):
            out_filename = name if (out_filename == '') else out_filename
            with open(os.path.join(out_path,out_filename),"w") as out_file:
               out_file.write(zfile.read(name))
      fh.close()

def create_metainfo(tmdb,filename,output):
   if (settings['config']['download_images'] == True):
      log('dowloading pictures for: '+filename,'info')
      download(settings['config']['tmdb_picture_link']+tmdb['backdrop_path'], os.path.join(output,'fanart.jpg'))
      download(settings['config']['tmdb_picture_link']+tmdb['poster_path'], os.path.join(output,'folder.jpg'))
   if (settings['config']['make_nfo_file'] == True):
      log('creating nfo file for: '+filename,'info')
      with open(os.path.join(output,os.path.splitext(filename)[0]+".nfo"), "w") as text_file:
         text_file.write('<?xml version="1.0" ?>\n')
         text_file.write('<movie>\n')
         text_file.write('<title>'+tmdb['title'].encode('utf-8')+'</title>\n')
         text_file.write('<id>'+tmdb['imdb_id']+'</id>\n')
         text_file.write('<runtime>'+str(tmdb['runtime'])+' min</runtime>\n')
         text_file.write('<year>'+tmdb['release_date'][:4]+'</year>\n')
         text_file.write('<plot>'+tmdb['overview'].encode('utf-8')+'</plot>\n')
         text_file.write('<tagline>'+tmdb['tagline'].encode('utf-8')+'</tagline>\n')
         text_file.write('<rating>'+str(tmdb['vote_average'])+'</rating>\n')
         text_file.write('<votes>'+str(tmdb['vote_count'])+'</votes>\n')
         text_file.write('<thumb>'+settings['config']['tmdb_picture_link']+tmdb['poster_path']+'</thumb>\n')
         if (len(tmdb['trailers']['youtube']) > 0) and (tmdb['trailers']['youtube'][0]['source'] != ""):
            text_file.write('<trailer>http://www.youtube.com/watch?v='+ tmdb['trailers']['youtube'][0]['source'] +'</trailer>\n')
         for genre in tmdb['genres']:
            text_file.write('<genre>'+genre['name'].encode('utf-8')+'</genre>\n')
         for cast in tmdb['cast']:
            text_file.write('<actor>\n   <name>'+cast['name'].encode('utf-8')+'</name>\n</actor>\n')
         for crew in tmdb['crew']:
            if (str(crew['job']).lower() == "director"):
               text_file.write('<director>'+crew['name'].encode('utf-8')+'</director>\n')
            else:
               text_file.write('<credits>'+crew['name'].encode('utf-8')+'</credits>\n')
         text_file.write('<videores>'+str(get_qual(filename))+'</videores>\n')
         text_file.write('</movie>')

def load_page_html(link,return_json=False):
   data = ""
   try:
      req = urllib2.Request(link)
      req.add_header('User-agent', 'Mozilla/5.0 Gecko/20100101 Firefox/22.0')
      req.add_header('Accept','text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8')
      req.add_header('Accept-Language','en-us;q=0.7,en;q=0.3')
      data = json.loads(urllib2.urlopen(req).read()) if return_json else urllib2.urlopen(req).read()
   except:
      log("error loading link: %s" % (link),'error')
   return data

def get_tmdb_data(imdb_id):
   log('retreiving metainfo from tmdb using imdbid: %s' % (imdb_id),'info')
   try:
      data = load_page_html(settings['config']['tmdb_server'] % (imdb_id, settings['config']['tmdb_api_key']),True)
      casts = load_page_html(settings['config']['tmdb_server'] % (imdb_id+"/casts", settings['config']['tmdb_api_key']),True)
      data['cast'] = casts['cast']
      data['crew'] = casts['crew']
   except:
      data = False
   return data

def is_locked(dirpath,filename):
    locked = True if (".mvn;" in ";".join(os.listdir(dirpath))) else False
    if os.path.isfile(os.path.join(dirpath,filename)) and (locked == False):
        file_object = try_except(open,[os.path.join(dirpath,filename), 'a', 8],filename+' is locked')
        locked = False if file_object else True
        if file_object:
           file_object.close()
    return locked

def log(data,logtype):
    if (logtype[:14] == "tracebackerror") or (logtype == "settingserror") or (("log_"+logtype in settings['config']) and (settings['config']['log_'+logtype] == True)):
       print data.encode('utf-8')
       data = data.encode('utf-8') if (logtype == "tracebackerror") else str(datetime.datetime.now()).split(".")[0]+': '+data.encode('utf-8')
       if not os.path.exists(os.path.join(home_folder,"logs")):
          os.makedirs(os.path.join(home_folder,"logs"))
       with open(os.path.join(home_folder,"logs","mf-"+str(datetime.date.today())+".log"), "a+") as myfile:
          myfile.write(data+'\n')

def try_except(function, arguments=[], failure_msg="Try error"):
    try:
        result = function(*arguments)
    except:
        result = False
        failure_msg = failure_msg+": %s(%s)" % (str(function),",".join(arguments)) if (failure_msg=="Try error") else failure_msg
        log(failure_msg,"error")
    return result

def rmfolder(dirpath, onlyfolder=False, remself=True):
    remfiles = "" if onlyfolder else " and files"
    log('deleting folders'+remfiles+' from: '+dirpath, "info")
    for root, dirs, files in os.walk(dirpath, topdown=False):
        if (onlyfolder == False):
           for name in files:
              log("removing: "+name,"info")
              try_except(os.remove,[os.path.join(root, name)],'file could not be removed: '+os.path.join(root, name))
        for name in dirs:
           log("removing: "+name,"info")
           try_except(os.rmdir,[os.path.join(root, name)],'folder not removed (not empty): '+os.path.join(root, name))
    if (remself == True):
       log("removing: "+dirpath,"info")
       try_except(os.rmdir,[dirpath],'folder not removed (not empty): '+dirpath)  

def get_imdbid(dirpath,frompath,movie_filename=None):
    imdb = re.findall("tt\\d{7}", dirpath)
    imdb_id = imdb[0] if (len(imdb) > 0) else "none"
    if (imdb_id == "none"):
       path = os.path.join(frompath,os.path.split(dirpath.replace(frompath,''))[1]) if (os.path.split(dirpath.replace(frompath,''))[0] == "/") else os.path.join(frompath,os.path.split(dirpath.replace(frompath,''))[0])
       for root, dirs, filenames in os.walk(path):
          for filename in filenames:
             if (str(os.path.splitext(filename)[1]).replace(".","").lower() in settings['config']['info_file_ext']) and (imdb_id == "none"):
                with open(os.path.join(root,filename)) as f:
                   imdb = re.findall("tt\\d{7}", str(f.readlines()))
                imdb_id = imdb[0] if (len(imdb) > 0) else imdb_id
    if (imdb_id == "none") and (movie_filename != None) and (settings['config']['search_web_id'] == True):
       search_link = settings['config']['g_search_url'] % (settings['config']['g_language'],movie_filename.replace(" ","+")+"+imdb")
       page_content = str(load_page_html(search_link,False))
       page_link = []
       if ('web_page_lookup' in settings['config']) and (len(settings['config']['web_page_lookup']) > 0):
          for lookup in settings['config']['web_page_lookup']:
             if (len(page_link) < 1):
                page_lookup = lookup['page_lookup']
                page_link = re.findall(lookup['g_result_find']+'"', page_content)
       page_content = removeNonAscii(load_page_html(page_lookup+page_link[0],False)) if (len(page_link) > 0) else ""
       imdb = re.findall("tt\\d{7}", page_content) if (movie_filename in page_content) else []
       imdb_id = imdb[0] if (len(imdb) > 0) else imdb_id
    return imdb_id

def download_trailer(video_id, dest_folder, filename):
   log('downloading trailer from youtube','info')
   try:
      querystring = urllib.urlencode({'asv':3,'el':'detailpage','hl':'en_US','video_id':video_id})
      response = urllib2.urlopen(settings['config']['yt_url'] + '?' + querystring)
      trailer_downloaded = False
      if response:
         data = urlparse.parse_qs(response.read().decode())       
         stream_map = parse_stream_map(data)
         video_urls = stream_map["url"]
         video_signatures = stream_map["sig"]
         for idx in range(len(video_urls)):
            try:
                fmt, data = extract_fmt(video_urls[idx])
            except (TypeError, KeyError):
                pass
            else:
                url = "%s&signature=%s" % (video_urls[idx], video_signatures[idx])
                if not trailer_downloaded:
                   trailer_ok = True
                   for key in settings['config']['yt_criteria'].keys():
                      if (data[key] != settings['config']['yt_criteria'][key]):
                         trailer_ok = False
                   if trailer_ok:
                      trailer_fn = os.path.splitext(filename)[0]+'-trailer.'+data['extension']
                      trailer_downloaded = download(url, os.path.join(dest_folder,trailer_fn))
      if not trailer_downloaded:
         log('no trailer found','info')
   except:
      log('error occured while trying to download trailer','error')

def parse_stream_map(data):
   videoinfo = {
            "itag": [],
            "url": [],
            "quality": [],
            "fallback_host": [],
            "sig": [],
            "type": []
   }
   if "url_encoded_fmt_stream_map" in data:
      text = data["url_encoded_fmt_stream_map"][0]
      videos = text.split(",")
      videos = [video.split("&") for video in videos]
      for video in videos:
         for kv in video:
            key, value = kv.split("=")
            videoinfo.get(key, []).append(urlparse.unquote(value))
   return videoinfo

def extract_fmt(text):
   itag = re.findall('itag=(\d+)', text)
   if itag and len(itag) is 1:
      itag = int(itag[0])
      attr = YT_ENCODING.get(itag, None)
      if not attr:
         return itag, None
      data = {}
      map(lambda k, v: data.update({k: v}), YT_ENCODING_KEYS, attr)
      return itag, data
                        
def rem_old_logfiles():
   if os.path.exists(os.path.join(home_folder,"logs")):
      os.chdir(os.path.join(home_folder,"logs"))
      for logFile in glob.glob("mf-*.log"):
         if os.stat(logFile).st_mtime < time.time() - 7 * 86400:
            os.remove(logFile)

def copyfile(SOURCE_FILENAME, TARGET_FILENAME):
   log("copying: "+SOURCE_FILENAME+" to "+TARGET_FILENAME,'info')
   if os.path.isfile(TARGET_FILENAME): os.remove(TARGET_FILENAME)
   if os.path.isfile(TARGET_FILENAME.replace(".mvn","")): os.remove(TARGET_FILENAME.replace(".mvn",""))
   source_size = os.stat(SOURCE_FILENAME).st_size
   copied = 0
   percent_copied = "0"
   source = open(SOURCE_FILENAME, 'rb')
   target = open(TARGET_FILENAME, 'wb')
   while True:
      chunk = source.read(32768)
      if not chunk:
         break
      target.write(chunk)
      copied += len(chunk)
      percent_copied = str(copied * 100 / source_size)
   source.close()
   target.close()

def get_qual(filename):
    qual = 719 if ("720i" in filename.lower()) else 0
    qual = 720 if ("720p" in filename.lower()) else qual
    qual = 1079 if ("1080i" in filename.lower()) else qual
    qual = 1080 if ("1080p" in filename.lower()) else qual
    return qual

def compare_qual(filename,dest_folder):
   src_qual = get_qual(filename)
   if src_qual > 0:
      os.chdir(dest_folder)
      for nfoFile in glob.glob("*.nfo"):
         with open(dest_folder+"/"+nfoFile) as f:
            dest_qual = re.findall("<videores>(.*?)</videores>", str(f.readlines()))
         if len(dest_qual) > 0:
            if isinstance( dest_qual[0], int ) and src_qual <= int(dest_qual[0]):
               return False
   return True

def find_files():
   file_found = False
   log('looking for files to move','info')
   for folders in settings['folders']:
      for dirpath, dirnames, filenames in os.walk(folders['from']):
         for filename in filenames:
            if (os.path.exists(dirpath)) and (not is_locked(dirpath,filename)) and (str(os.path.splitext(filename)[1]).replace(".","") in settings['config']['file_ext']):
               file_size = os.path.getsize(os.path.join(dirpath,filename)) >> 20
               if (file_size >= settings['config']['file_size_min']) and (file_size <= settings['config']['file_size_max']):
                  file_found = True
                  imdb_id = get_imdbid(dirpath,folders['from'],filename)
                  if (imdb_id[:2] == "tt"):
                     log('found: '+filename+' - '+imdb_id,'info')
                     new_better = True
                     tmdb = get_tmdb_data(imdb_id)
                     if tmdb:
                        dest_folder = os.path.join(folders['to'],tmdb['title'].replace(':',' -')+" ("+tmdb['release_date'][:4]+")") if (not settings['config']['moveto_year_folder']) else os.path.join(folders['to'],tmdb['release_date'][:4],tmdb['title'].replace(':',' -'))
                     else:
                        log("imdb id: "+imdb_id+" - found for "+os.path.join(dirpath,filename)+", but could not retreive any data from tmdb","info")
                        dest_folder = os.path.join(folders['to'],imdb_id) if (not settings['config']['moveto_year_folder']) else os.path.join(folders['to'],"unknown",imdb_id)
                     if (tmdb) or ((not tmdb) and (settings['config']['move_without_metadata'])):
                        if not os.path.exists(dest_folder):
                           os.makedirs(dest_folder) 
                        else:
                           new_better = compare_qual(filename,dest_folder)
                           if new_better:
                              rmfolder(dest_folder,False,False)
                        if (settings['config']['download_subtitles']) and (not os.path.isfile(os.path.join(dest_folder,os.path.splitext(filename)[0]+".srt"))):
                           download_subs(imdb_id,filename,dest_folder)
                        if (tmdb): 
                           if (not os.path.isfile(os.path.join(dest_folder,os.path.splitext(filename)[0]+".nfo"))):
                              create_metainfo(tmdb,filename,dest_folder)
                           if (settings['config']['download_trailer'] == True) and (len(tmdb['trailers']['youtube']) > 0) and (tmdb['trailers']['youtube'][0]['source'] != ""):
                              download_trailer(tmdb['trailers']['youtube'][0]['source'],dest_folder,filename)
                        if (new_better) and ((not os.path.isfile(os.path.join(dest_folder,filename))) or (os.path.getsize(os.path.join(dirpath,filename)) != os.path.getsize(os.path.join(dest_folder,filename)))):
                           copyfile(os.path.join(dirpath,filename), os.path.join(dest_folder,filename+".mvn"))
                        if (os.path.isfile(os.path.join(dest_folder,filename+".mvn")) and (os.path.getsize(os.path.join(dirpath,filename)) == os.path.getsize(os.path.join(dest_folder,filename+".mvn")))) or (os.path.isfile(os.path.join(dest_folder,filename)) and (os.path.getsize(os.path.join(dirpath,filename)) == os.path.getsize(os.path.join(dest_folder,filename)))):  
                           log(filename+' succesfully moved to: '+dest_folder,'info')
                           if (os.path.isfile(os.path.join(dest_folder,filename+".mvn"))) and (not os.path.isfile(os.path.join(dest_folder,filename))):
                              os.rename(os.path.join(dest_folder,filename+".mvn"),os.path.join(dest_folder,filename))
                           if settings['config']['cleanup_after_move']:
                              if (dirpath != folders['from']):
                                 rmfolder(dirpath,False,True)
                              else:
                                 os.remove(os.path.join(dirpath,filename))
                           else:
                              os.remove(os.path.join(dirpath,filename))
                        else:
                           log_msg = ['error occured while trying to move: '+os.path.join(dirpath,filename)+' at '+percent_copied+'%','error'] if (not new_better) else ['a better version of '+tmdb['title']+' already exists','info']
                           if (not new_better) and (settings['config']['cleanup_after_move']):
                              if (dirpath != folders['from']):
                                 rmfolder(dirpath,False,True)
                              else:
                                 os.remove(os.path.join(dirpath,filename))
                           log(*log_msg)
                  else:
                     log("no imdb id found for: "+os.path.join(dirpath,filename),'info')
      if os.listdir(folders['from']) != []: 
         if file_found:
            rmfolder(folders['from'],True,False)
         elif settings['config']['cleanup_at_end']:
            rmfolder(folders['from'],False,False)

def load_settings():
   str_settings = ""
   try:
      with open(os.path.join(home_folder,"settings.json")) as data:
         for line in data:
            str_settings += line.rstrip('\r\n').replace("  ","")
      str_settings = json.loads(str_settings)
   except Exception as inst:
      log("error in settings file: "+inst.args,'settingserror')
   return str_settings

settings = load_settings()
rem_old_logfiles()
if not os.path.isfile(os.path.join(home_folder,'move.run')):
   with open(os.path.join(home_folder,'move.run'), "w") as text_file:
      text_file.write('running')
   if ("folders" in settings) and ("config" in settings):
      try:
         find_files()
      except Exception as inst:
         exc_type, exc_value, exc_traceback = sys.exc_info()
         log("Traceback error:","tracebackerror_start")
         for line in traceback.format_exception(exc_type, exc_value, exc_traceback):
            log(line.rstrip('\r\n'),"tracebackerror")
   else:
      log("error loading settings!","settingserror")
   os.remove(os.path.join(home_folder,'move.run'))
else:
   print("move_done already running!")
