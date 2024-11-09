R='\e[01;91m'
G='\e[01;92m'
Y='\e[01;93m'
LG='\e[01;37m'
N='\e[0m'
L='\033[7m'
X='\033[0m'

print_header() {
    clear
    echo -e "${LG}------------------------------------------------${N}\n"
}

# Function to update packages
update_packages() { 
    echo -e "${Y}${L}\n Updating... \n${N}"
    pkg update && pkg upgrade -y
    clear
}

# Function to install Python and dependencies
install_python() {
    pkg install python-pip -y
    clear
}

# Function to install Jq
install_jq() {
    echo -e "${Y}${L}\n Installing jq... \n${N}"
    pkg install jq -y
    clear
}

# Function to install ffmpeg
install_ffmpeg() {
    echo -e "${Y}${L}\n Installing ffmpeg... \n${N}"
    pkg install ffmpeg -y
    clear
}

# Function to install mpv
install_mpv() {
    echo -e "${Y}${L}\n Installing mpv... \n${N}"
    pkg install mpv -y
    clear
}

# Function to install wget
install_wget() {
    echo -e "${Y}${L}\n Installing wget... \n${N}"
    pkg install wget -y
    clear
    sleep 0.2
}

# Function to install YouTube-dl
install_youtube_dl() {
    echo -e "${Y}${L}\n Installing YouTube-dl... \n${N}"
    pip install yt-dlp
    pip install yt-dlp -U
    clear
}

# Function to set up configurations
setup_configs() {
    echo -e "${Y}${L}\n Setting up configs... $G JuniorSir \n${N}"
    sleep 2
    echo -e "${Y}${L}\n Creating Web Videos folder... \n${N}"
    mkdir -p ~/storage/webvideos
    sleep 1.5
    echo -e "${Y}${L}\n Creating youtube-dl config... \n${N}"
    rm -rf ~/.config/yt-dlp
    mkdir -p ~/.config/yt-dlp
    sleep 1.5
    echo -e "${Y}${L}\n Getting config file... \n${N}"
    wget -q https://raw.githubusercontent.com/juniorsir/Download-from-anywhere-/main/config -P ~/.config/yt-dlp
    cd ~/.config/yt-dlp || exit 1
    chmod +x config
    sleep 1
}

# Function to set up executable scripts
setup_executables() {
    echo -e "${Y}${L}\n Creating bin folder... \n${N}"
    sleep 1.5
    echo -e "${Y}${L}\n Getting files...\n${N}"
    rm -rf /data/data/com.termux/files/usr/bin/web
    wget https://raw.githubusercontent.com/juniorsir/Download-from-anywhere-/main/web.sh
    mv web.sh /data/data/com.termux/files/usr/bin/web || exit 1
    chmod +x /data/data/com.termux/files/usr/bin/web
    clear
    echo -e "${Y}${L}\n Creating bin folder... \n${N}"
    mkdir -p ~/bin
    sleep 1.5
    echo -e "${Y}${L}\n Getting files...\n${N}"
    rm -rf ~/bin/termux-url-opener
    pkg install wget -y
    wget -q https://raw.githubusercontent.com/juniorsir/Termux-background-player/main/termux-url-opener -P ~/bin
    cd ~/bin || exit 1
    chmod +x termux-url-opener
}

# Main execution flow
main() {
    print_header
    update_packages
    print_header
    echo -e "${Y}${L}\n YouTube-dl Installer By $G JuniorSir \n${N}"
    install_python
    echo -e "${Y}${L}\n Installing ffmpeg... \n${N}"
    install_ffmpeg
    update_packages
    install_mpv
    install_wget
    install_youtube_dl
    setup_configs
    setup_executables
    echo -e "${Y}${L}\n Finishing configuration... $G JuniorSir \n${N}"
    sleep 3.5
    echo -e "${G}\n Installation Finished...\n${N}"
     sleep 3.5
    echo -e "${G}\n Gp to Termux app Settings and Allow Display over other apps \n${N}"
    echo -e "${G}\n 1) Open YouTube or any website playlist/video \n${N}"
    echo -e "${G}\n 2) Click on share button And use select termux \n${N}"
    echo -e "${G}\n 3) Now, copy the share url \n${N}"
    echo -e "${G}\n 4) Go to termux and type (for copied URL) ${R}"web" and paste url then enter \n${N}"
    kill -1 $PPID
}

# Execute main function
main
