#!/bin/bash

#JuniorSir

# Colors                                                                                                                                                       # ----------------------------------------                                                                                                                     BL='\e[01;90m' > /dev/null 2>&1; # Black
R='\e[01;91m' > /dev/null 2>&1; # Red
G='\e[01;92m' > /dev/null 2>&1; # Green
Y='\e[01;93m' > /dev/null 2>&1; # Yellow                                                                                                                       B='\e[01;0m' > /dev/null 2>&1; # Blue
P='\e[01;95m' > /dev/null 2>&1; # Purple
C='\e[01;96m' > /dev/null 2>&1; # Cyan
W='\e[01;0m' > /dev/null 2>&1; # White
LG='\e[01;37m' > /dev/null 2>&1; # Light Gray
N='\e[0m' > /dev/null 2>&1; # Null
L='\033[7m' > /dev/null 2>&1; #Lines
X='\033[0m' > /dev/null 2>&1; #Closer
# ----------------------------------------

clear

# Check if yt-dlp is installed
if ! command -v yt-dlp &> /dev/null
then
    echo "yt-dlp not found. Please install it first."
    sleep 2
    echo -e $G "yt-dlp is InStaLling...."
    pip install youtube-dl
# or
    pip install yt-dlp

fi

# Prompt user for URL
 echo -e $G
read -p "Enter the video URL: " URL


# Ask for user confirmation
read -p "Plese select the content type.. [adult/normal]: " RESPONSE

# Check user response
if [[ "$RESPONSE" == "adult" || "$RESPONSE" == "Adult" ]]
then
    echo "Proceeding..."

    QUALITY="${2:-best}" # Default to 'best' quality if not provided

# Download video with specified quality
yt-dlp -f "$QUALITY" "$URL"
  exit    

# Add any additional actions here                               
else
    echo "Wait..."
   fi

# Use yt-dlp to get video information
INFO=$(yt-dlp --print-json "$URL")

# Extracting required information from JSON output
TITLE=$(echo "$INFO" | jq -r '.title')
UPLOADER=$(echo "$INFO" | jq -r '.uploader')
UPLOAD_DATE=$(echo "$INFO" | jq -r '.upload_date')
VIDEO_URL=$(echo "$INFO" | jq -r '.webpage_url')

# Display the information
echo -e $G "Video Title: $TITLE"
echo -e $G "Uploaded By: $UPLOADER"
echo -e $G "Upload Date: $UPLOAD_DATE"
echo -e $G "Video URL: $VIDEO_URL"

# Ask for user confirmation
read -p "Do you want to continue? (y/n): " RESPONSE

# Check user response
if [[ "$RESPONSE" == "y" || "$RESPONSE" == "Y" ]]
then
    echo "Proceeding..."
    # Add any additional actions here
else
    echo "Exiting."
    exit 0
fi


# Check if URL is provided
if [ -z "$URL" ]; then
    echo -e ${L}${G}"\n  Please! use this format- bash web.sh <URL>..\n"$N
    exit 1
fi

echo ""
echo -e $R"          _  _   _   _   _   _  "$N
echo -e $R"      _ /   / \ / \ / \ / \ / \ "$N
echo -e $Y"      _    ( + | S | I | R | + )"$N
echo -e $R"        \ _ \_/ \_/ \_/ \_/ \_/ "$N

echo -e $C "╔════════════════════════════════════════╗"
echo -e $G "║ ==> Project Name  :Termux-YDL          ║"
echo -e $G "║ ==> Author        :JuniorSir           ║"
echo -e $G "║ ==> Github                             ║"
echo -e $G "║ ==> Telegram      :juniorsir_bot       ║"
echo -e $C "╠════════════════════════════════════════╝"
echo -e $C "╠═▶ [ Select Format:: ]"
echo -e $G "╠═▶ [1] Music Mp3♫"
echo -e $G "╠═▶ [2] Video 360p"
echo -e $G "╠═▶ [3] Video 480p"
echo -e $G "╠═▶ [4] Video 720p"
echo -e $G "╠═▶ [5] Video 1080p"
echo -e $G "╠═▶ [6] Video 2160p"
echo -e $G "╠═▶ [7] Play Background"
echo -e $G "╠═▶ [8] Exit Termux-YDL"
printf "$G ╚═➤  $W"

while :
do

    read INPUT_STRING
    case $INPUT_STRING in

        1)
            echo "-x --no-mtime -o /data/data/com.termux/files/home/storage/webvideos/%(title)s.%(ext)s -f \"bestaudio\" --extract-audio --audio-format mp3 --audio-quality 0" > ~/.config/yt-dlp/config
            termux-toast "Downloading...🤗"
            yt-dlp $URL
            echo -e $G"\n   Finished...\n"$N
            termux-toast "Downloaded...😚"
            sleep 1
            exit
        ;;

        2)

            echo "--no-mtime -o /data/data/com.termux/files/home/storage/webvideos/%(title)s.%(ext)s -f \"bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]\"" > ~/.config/yt-dlp/config
            termux-toast "Downloading...🤗"
            yt-dlp $URL
            echo -e $G"\n   Finished...\n"$N
            termux-toast "Downloaded...😚"
            sleep 1
            exit
        ;;

        3)
            echo "--no-mtime -o /data/data/com.termux/files/home/storage/webvideos/%(title)s.%(ext)s -f \"bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]\"" > ~/.config/yt-dlp/config
            termux-toast "Downloading...🤗"
            yt-dlp $URL
            echo -e $G"\n   Finished...\n"$N
            termux-toast "Downloaded...😚"
            sleep 1
            exit
        ;;
        4)
            echo "--no-mtime -o /data/data/com.termux/files/home/storage/webvideos/%(title)s.%(ext)s -f \"bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]\"" > ~/.config/yt-dlp/config
            termux-toast "Downloading...🤗"
            yt-dlp $URL
            echo -e $G"\n   Finished...\n"$N
            termux-toast "Downloaded...😚"
            sleep 1
            exit
        ;;

        5)
            echo "--no-mtime -o /data/data/com.termux/files/home/storage/webvideos/%(title)s.%(ext)s -f \"bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]\"" > ~/.config/yt-dlp/config
            termux-toast "Downloading...🤗"
            yt-dlp $URL
            echo -e $G"\n   Finished...\n"$N
            termux-toast "Downloaded...😚"
            sleep 1
            exit
        ;;

        6)
            echo "--no-mtime -o /data/data/com.termux/files/home/storage/webvideos/%(title)s.%(ext)s -f \"bestvideo[height<=2160][ext=mp4]+bestaudio[ext=m4a]\"" > ~/.config/yt-dlp/config
            termux-toast "Downloading...🤗"
            yt-dlp $URL
            echo -e $G"\n   Finished...\n"$N
            termux-toast "Downloaded...😚"
            sleep 1
            exit
        ;;

        7)
            termux-toast "Background playing...🎧"
            mpv $URL
            echo -e $G"\n   Finished...\n"$N
            sleep 1
            exit
        ;;

        8)

            break
        ;;

        *)

            echo -e "$R\n   Wrong input! Please Enter again::\n$W"
    esac
done



