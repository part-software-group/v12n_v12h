#!/usr/bin/env python3
import os, sys, argparse, string, shutil, random
import socket, libvirt, subprocess, hashlib, json

my_name = '[v12h]'
my_version = ''
v12n_home = '/v12n/'
local_libvirt = '/.local/share/libvirt/'
show, password_num = False, 12

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m' + my_name
    KBLUE = '\033[94m'
    OKGREEN = '\033[92m' + my_name
    WARNING = '\033[93m' + my_name
    FAIL = '\033[91m' + my_name
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def check_root():
    """some functions need root permission"""
    if os.geteuid() != 0:
        sys.exit(bcolors.FAIL + ' error: must be root' + bcolors.ENDC)

def su_as_domain(domain, command):
    """su as user that runs domain"""
    check_root()
    if domain:
        r = subprocess.call(['su', '-', domain, '-c', command])
        if args.verbose:
            print(bcolors.OKGREEN, command, r, bcolors.ENDC)
    else:
        print(bcolors.WARNING, 'no domain name specified' + bcolors.ENDC)
    if r == 0:
        return(True)
    else:
        return(False)

def password_gen(size):
    """generating random password. copied form stack"""
    return ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(size))

def md5(fname):
    """md5 the iso. copied form stack"""
    hash_md5 = hashlib.md5()
    with open(fname, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def vnc_port():
    """return available vnc port between 5900 to 5999. some copied from stack"""
    random_port = random.randint(5900, 5999)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(('localhost', random_port)) != 0:
            return(random_port)

def new_user(user, user_home):
    """adding linux user"""
    check_root()
    password = password_gen(password_num)
    if args.show:
        print(bcolors.OKGREEN,
              'creating user', user, 'with password', password +
              bcolors.ENDC)
    else:
        print(bcolors.OKGREEN, 'creating user', user + bcolors.ENDC)
    r = subprocess.call(['useradd', '--comment', 'added_by_v12h',
                         '--create-home', '--home-dir', user_home,
                         '--no-user-group', '--group', 'kvm',
                         '--key', 'UID_MIN=2001',
                         '--key', 'UID_MAX=2050',
                         user])
    if r == 0:
        print(bcolors.OKGREEN,
              'user', user, 'created successfully' + bcolors.ENDC)
    else:
        sys.exit(bcolors.FAIL + ' error: adduser failed' + bcolors.ENDC)
    p1 = subprocess.Popen(['echo', user + ':' + password],
                           stdout=subprocess.PIPE)
    p2 = subprocess.Popen(['chpasswd' ], stdin=p1.stdout)
    p1.stdout.close()
    output = p2.communicate()[0]
    os.makedirs(user_home + local_libvirt)
    os.chmod(user_home, 0o750)
    subprocess.call(['chown', '-R', user + ':' + 'kvm', user_home])
    print(bcolors.OKGREEN, '$HOME is ' + user_home + bcolors.ENDC)

def remove_user(user):
    """removes everything"""
    check_root()
    print( bcolors.FAIL, 'removing user', user, bcolors.ENDC)
    subprocess.call(['pkill', '-u', user])
    subprocess.call(['deluser', '--remove-home', user])
    print( bcolors.FAIL, 'removing', user, 'home', bcolors.ENDC)
    try:
        shutil.rmtree(v12n_home + user)
    except FileNotFoundError as e:
        sys.exit(bcolors.FAIL + v12n_home + user +
                 ' is already removed. nevermind ...' + bcolors.ENDC)

def packer_json(user, user_home, packer_tmpl, dicted):
    shutil.copytree(v12n_home + '/.packer/qemu', user_home + '/.packer/qemu')
    jtmpfile = user_home + '/.packer/qemu/debian/' + packer_tmpl
    with open(jtmpfile, 'r') as json_file:
        json_data = json.load(json_file)
        for key in dicted:
            try:
                val = dicted[key]
            except KeyError as e:
                print(bcolors.FAIL, e, bcolors.ENDC)
                remove_user(user)
            json_data['variables'][key] = val
            if args.verbose:
                print(bcolors.OKGREEN, key + ' set to ' + val, bcolors.ENDC)
    with open(jtmpfile, 'w') as json_file:
        json_file.write(json.dumps(json_data, indent=2))

def new_domain(domain, user_home, packer_tmpl):
    """creating domain with the help of packer"""
    print(bcolors.OKGREEN, 'creating domain with user', domain + bcolors.ENDC)
    if su_as_domain(domain, 'cd ' + user_home + '/.packer/qemu/debian&&' +
                'packer build ' + packer_tmpl):
        print(bcolors.OKGREEN, 'image created successfully' + bcolors.ENDC)
    else:
        print(bcolors.FAIL, 'something went wrong. cleaning ...' + bcolors.ENDC)
        remove_user(domain)

def new_iso(user, user_home, iso):
    """using iso"""
    os.makedirs(user_home + local_libvirt + '/images')

def virt_install(mode, user, dicted):
    domain = user
    try:
        cpu = dicted['cpu'] + ',maxvcpus=' + dicted['xcpu']
        memory = dicted['memory'] + ',maxmemory=' + dicted['xmemory']
        vnc = 'vnc,port=' + dicted['vnc']
        net = 'bridge=' + dicted['br'] + ',model=virtio'
    except KeyError as e:
        print(bcolors.FAIL, e, bcolors.ENDC)
        remove_user(user)
    default_opts = ['virt-install', '--connect', 'qemu:///session',
                    '--noautoconsole', '--virt-type', 'kvm', '--cpu', 'host',
                    '--boot', 'hd', '--name', domain, '--vcpus', cpu,
                    '--memory', memory, '--network', net,
                    '--graphics', vnc, ' ']
    cmd_default = ' '.join(default_opts)
    if mode == 'image':
        image_opts = ['--disk',
                      'format=raw,bus=virtio,cache=none,io=native,path=']
        image_args = ['$HOME', local_libvirt, '/images/',
                      dicted['hostname'], '.raw']
        cmd_image = ' '.join(image_opts)
        image = ''.join(image_args)
        virt_install_image = cmd_default + cmd_image + image
        print(bcolors.OKGREEN, 'installing image using virt-install',
              bcolors.ENDC)
        if su_as_domain(domain, virt_install_image):
            print(bcolors.OKGREEN, "vnc port is:", vnc, bcolors.ENDC)
            return True
        else:
            return False
    if mode == 'iso':
        poolb = 'pool=default,format=raw,bus=virtio,cache=none,io=native,size='
        try:
            poolz = ',size=' + dicted['size']
            iso_opts = ['--cdrom', dicted['iso'], '--disk',
                        poolb + dicted['size']]
        except KeyError as e:
            print(bcolors.FAIL, 'key', e, 'not found', bcolors.ENDC)
            remove_user(user)
        cmd_iso = ' '.join(iso_opts)
        virt_install_iso = cmd_default + cmd_iso
        if su_as_domain(domain, virt_install_iso):
            print(bcolors.OKGREEN, "vnc port:", dicted['vnc'], bcolors.ENDC)
            return True
        else:
            return False

def to_dict(the_list):
    the_dict = {}
    first = the_list.split(',')
    i = 0
    while i < len(first):
        try:
            sec = first[i].split('=')
            key = sec[0]
            val = sec[1]
            the_dict[key] = val
            i += 1
        except IndexError:
            sys.exit(bcolors.FAIL + ' extra , perhaps' + bcolors.ENDC)
    return(the_dict)

def after_dict(mode, dicted, user):
    key_necss = ['cpu', 'memory', 'size', 'br', 'iso']
    try:
        key_defaults = {'vnc': str(vnc_port()), 'xcpu': dicted['cpu'],
                        'xmemory': dicted['memory'], 'hostname': user,
                        'domain': socket.getfqdn(), 'md5': md5(dicted['iso']),
                        'apt_proxy': 'debian.asis.io'}
    except KeyError:
        pass

    if mode == 'check':
        for keyn in key_necss:
            if keyn not in dicted:
                print(bcolors.FAIL, 'these keys MUST be present at --set:',
                      str(key_necss), bcolors.ENDC)
                sys.exit(bcolors.FAIL + ' you forgot ' + bcolors.BOLD +
                         keyn + bcolors.ENDC)
        return(True)
    if mode == 'fix':
        for keyd in key_defaults:
            try:
                dicted[keyd]
            except KeyError:
                dicted[keyd] = key_defaults[keyd]
        return(dicted)

def hv_up(packer_git):
    """setup all needed for a host to be a kvm hv"""
    check_root()
    if not os.path.exists(v12n_home):
        os.makedirs(v12n_home + '/.iso')
    if not os.path.exists('/etc/qemu'):
        os.makedirs('/etc/qemu')
        print(bcolors.OKGREEN, v12n_home, 'created' + bcolors.ENDC)
    subprocess.call(['apt-get', 'update'])
    subprocess.call(['apt-get', '--yes', '--no-install-recommends', 'install',
                     'atop', 'htop', 'git', 'screen', 'udhcpd', 'packer',
                     'parted', 'qemu-utils', 'qemu-kvm', 'libguestfs-tools',
                     'libvirt-clients', 'libvirt-daemon-system',
                     'virtinst', 'bridge-utils' ] )
    subprocess.call(['git', '-C', v12n_home, 'clone',
                     '--depth', '1', packer_git, v12n_home + '.packer'])

def setup_bridge(br_on, br_if, br_ip, br_bg):
    """setting up bridge interface and qemu related stuff"""
    check_root()
    bo = str(br_on)
    bf = str(br_if)
    bi = str(br_ip)
    bg = str(br_bg)
    subprocess.call(['mv', '/etc/network/interfaces',
                           '/etc/network/interfaces.old'])
    with open('/etc/network/interfaces', 'w+') as lo:
        lo.write('# added by v12h\n'
                 'auto lo\n'
                 'iface lo inet loopback\n'
                 'source-directory /etc/network/interfaces.d\n')
    with open('/etc/network/interfaces.d/' + bf, 'w+') as br:
        br.write('# added by v12h\n'
                 'auto ' + bf + '\n'
                 'iface ' + bf + ' inet static\n'
                 '  address ' + bi + '\n'
                 '  gateway ' + bg + '\n'
                 '  bridge_ports ' + bo + '\n'
                 '  bridge_stp off\n'
                 '  bridge_fd 0\n')
    with open('/etc/qemu/bridge.conf', 'w+') as bc:
        bc.write('# added by v12h\n'
                 'allow ' + bf + '\n')
    subprocess.call(['ip', 'address', 'flush', bo, 'scope', 'global'])
    subprocess.call(['ifup', bf])
    subprocess.call(['setcap',
                     'cap_net_admin+ep',
                     '/usr/lib/qemu/qemu-bridge-helper'])

def get_conn(user):
    try:
        conn = libvirt.open('qemu+unix:///session?socket=' +
                            v12n_home + user +
                            '/.cache/libvirt/libvirt-sock')
    except libvirt.libvirtError as e:
        sys.exit(bcolors.FAIL + ' could not connect' + bcolors.ENDC)
    if conn == None:
        sys.exit(bcolors.FAIL +
                 ' failed to open connection to qemu:///session' +
                 bcolors.ENDC)
    else:
        return(conn)

def dom_status(conn):
    domains = conn.listAllDomains(0)
    for domain in domains:
        state, reason = domain.state()
        if state == libvirt.VIR_DOMAIN_RUNNING:
            state = 'active'
        if state == libvirt.VIR_DOMAIN_SHUTDOWN:
            state = 'shutdown'
        if state == libvirt.VIR_DOMAIN_SHUTOFF:
            state = 'destroyed'
        print(bcolors.OKGREEN, domain.name(), 'status:', state, bcolors.ENDC)
    conn.close()

def dom_act(conn, user, act):
    dom = conn.lookupByName(user)
    acts = {'start': 'dom.create()',
            'stop': 'dom.destroy()'}
    try:
        if args.verbose:
            print(acts[act])
        exec(acts[act])
        print(bcolors.OKGREEN, dom.name(),
              'successfull', act, bcolors.ENDC)
    except libvirt.libvirtError as e:
        pass
    conn.close()

def dom_info(conn, user):
    dom = conn.lookupByName(user)
    infos = {'name': dom.name(),
             'uuid': dom.UUIDString(),
             'cpu': dom.info()[3],
             'max cpu': dom.maxVcpus(),
             'memory': dom.info()[2],
             'max memory': dom.info()[1],
             'time': dom.getTime()}
    for info in infos:
        print(bcolors.OKGREEN, info + ':', infos[info], bcolors.ENDC)
    conn.close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--verbose', '-v', help='verbose', action='store_true')
    parser.add_argument('--new-domain', help='add new domain')
    parser.add_argument('--packer', help='packer template to use',
                        nargs='?', const='buster.json',
                        choices = [ 'buster.json', 'stretch.json' ] )
    parser.add_argument('--set', help='cpu, memory, size, vnc, br, iso')
    parser.add_argument('--new-iso', help='username')
    parser.add_argument('--remove-user', help='remove everthing')

    parser.add_argument('--show', help='show password', action='store_true')
    parser.add_argument('--virsh', '-r', help='virsh of domain',
                        nargs='?', const=os.environ.get('USER'))
    parser.add_argument('--edit', '-e', help='edit domain xml')
    parser.add_argument('--console', '-n', help='console to domain')
    parser.add_argument('--status', '-u', help='domain status',
                        nargs='?', const=os.environ.get('USER'))
    parser.add_argument('--start', '-s', help='start domain',
                        nargs='?', const=os.environ.get('USER'))
    parser.add_argument('--stop', '-d', help='stop domain',
                        nargs='?', const=os.environ.get('USER'))
    parser.add_argument('--info', '-i', help='domain info',
                        nargs='?', const=os.environ.get('USER'))

    parser.add_argument('--add-bridge', help='if=?,br=?,ip=?,bg=?')
    parser.add_argument('--hv-up', help='rise up', action='store_true')
    parser.add_argument('--packer-git', help='packer git address')
    parser.add_argument('--new-user', help='add new user')
    parser.add_argument('--test')
    global args
    args = parser.parse_args()

    if len(sys.argv) < 2 or args.status:
        dom_status(get_conn(os.environ.get('USER')))

    if args.virsh:
        su_as_domain(args.virsh, 'virsh')
    if args.edit:
        su_as_domain(args.edit, 'virsh edit ' + args.edit)
    if args.console:
        su_as_domain(args.console, 'virsh console ' + args.console)
    if args.start:
        user = args.start
        dom_act(get_conn(user), user, 'start')
    if args.stop:
        user = args.stop
        dom_act(get_conn(user), user, 'stop')
    if args.info:
        user = args.info
        dom_info(get_conn(user), user)

    if args.new_user:
        user = args.new_user
        user_home = v12n_home + user
        new_user(user, user_home)

    if args.new_domain:
        user = args.new_domain
        user_home = v12n_home + user
        if args.packer:
            packer_tmpl = args.packer
        else:
            sys.exit(bcolors.FAIL +
                     ' error: packer template name is not specified.'
                     ' user --packer' +
                     bcolors.ENDC)
        if args.set:
            dicted = to_dict(args.set)
            if after_dict('check', dicted, user):
                dicted = after_dict('fix', dicted, user)
                new_user(user, user_home)
                packer_json(user, user_home, packer_tmpl, dicted)
                new_domain(user, user_home, packer_tmpl)
                virt_install('image', user, dicted)
            else:
                remove_user(user)
        else:
            sys.exit(bcolors.FAIL +
                     ' error: use --set with --new-domain' + bcolors.ENDC)

    if args.new_iso:
        user = args.new_iso
        user_home = v12n_home + user
        if args.set:
            dicted = to_dict(args.set)
            if after_dict('check', dicted, user):
                dicted = after_dict('fix', dicted, user)
                new_user(user, user_home)
                virt_install('iso', user, dicted)
            else:
                remove_user(user)
        else:
            sys.exit(bcolors.FAIL +
                     ' error: use --set with --new-iso' + bcolors.ENDC)

    if args.remove_user:
        remove_user(args.remove_user)

    if args.add_bridge:
        try:
            bridge = []
            i = 0
            first = args.add_bridge.split(',')
            while i < len(first):
                sec = first[i].split('=')
                bridge.append(sec[1])
                i += 1
            setup_bridge(br_on = bridge[0],
                         br_if = bridge[1],
                         br_ip = bridge[2],
                         br_bg = bridge[3])
        except IndexError as e:
            sys.exit(bcolors.FAIL + ' error: if=?,br=?,ip=?,bg=?' +
                     bcolors.BOLD + ' order and subnet is important.' + e +
                     bcolors.ENDC)

    if args.hv_up:
        if args.packer_git:
            hv_up(args.packer_git)
        else:
            sys.exit(bcolors.FAIL +
                     ' error: packer git address is not specified' +
                     bcolors.ENDC)

if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit as sys_e:
        sys.exit(sys_e.code)
    except KeyboardInterrupt:
        logging.debug('', exc_info=True)
        print_stderr(_('aborted at user request'))
    #except Exception as main_e:
     #   fail(main_e)
