import urllib.request
try:
    print("URLLIB_SAW:" + urllib.request.urlopen("https://api.ipify.org", timeout=25).read().decode())
except Exception as e:
    print("URLLIB_ERR:" + type(e).__name__ + ":" + str(e)[:90])
