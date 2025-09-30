Vagrant.configure("2") do |config|
  # Base OS
  config.vm.box = "ubuntu/focal64"

  # VM settings
  config.vm.provider "virtualbox" do |vb|
    vb.name = "qsdn-poc"
    vb.memory = "4096"   # 4 GB RAM
    vb.cpus = 2
  end

  # Port forwarding (if you want to connect from host → Ryu controller in VM)
  config.vm.network "forwarded_port", guest: 6633, host: 6633   # OpenFlow
  config.vm.network "forwarded_port", guest: 8080, host: 8080   # Web UIs (if any)

  # Provisioning script
  config.vm.provision "shell", inline: <<-SHELL
    # Update system
    sudo apt-get update -y

    # Install Mininet
    git clone https://github.com/mininet/mininet
    cd mininet
    git tag  # list available versions
    git checkout -b mininet-2.3.0 2.3.0  # or whatever version you wish to install
    cd ..
    mininet/util/install.sh -a

    # Install Python & Pip
    sudo apt-get install -y python3 python3-pip python3-venv git

    # Install Ryu
    git clone https://github.com/faucetsdn/ryu.git
    cd ryu
    pip install .

    # Install QuNetSim (quantum network simulator)
    git clone git@github.com:tqsd/QuNetSim.git
    python3 -m venv venv
	source ./venv/bin/activate
	pip install --upgrade pip
	pip install -r ./QuNetSim/requirements.txt
	export PYTHONPATH=$PYTHONPATH:/home/qsdn/QuNetSim

    

    echo "✅ Environment ready! Run 'vagrant ssh' to log in."
    echo "➡️  Example: ryu-manager ~/qsdn/ryu_app/my_controller.py"
    echo "➡️  Example: sudo mn --custom ~/qsdn/mininet_scripts/topo.py --controller=remote"
  SHELL
end
