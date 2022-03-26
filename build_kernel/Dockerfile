FROM ubuntu:xenial-20200212

# Refresh local packages cache.
RUN apt-get update

# Install packages.
RUN apt-get install --no-install-recommends -y \
    sudo make gcc-arm-none-eabi gcc g++ libc6-dev \
    device-tree-compiler bison flex python3 python3-dev \
    swig cpio lzma bc kmod libgmp-dev libssl-dev \
    ca-certificates vim git gdb-arm-none-eabi \
    libglib2.0-dev libpixman-1-dev libmpc-dev abootimg wget

# From now on we will work as regular user. First add user.
RUN useradd -m -d /home/user -s /bin/bash -G sudo user
RUN echo user:pass | chpasswd
RUN sudo echo "user ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers

# Make new user active.
USER user
WORKDIR /home/user
RUN wget "https://developer.arm.com/-/media/Files/downloads/gnu-rm/10.3-2021.10/gcc-arm-none-eabi-10.3-2021.10-x86_64-linux.tar.bz2" && \
    tar -xvf "gcc-arm-none-eabi-10.3-2021.10-x86_64-linux.tar.bz2" && \
    git clone "https://gitlab.com/antoni.aloytorrens/android-tf101-tools/"
COPY make_tegra.sh /home/user
