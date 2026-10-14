"""Minimal litematic reader: {(x,y,z): 'id[props]'} for non-air blocks, plus '_size' and '_tes'."""
import gzip, struct, sys, glob, os, json

def read_nbt(data):
    pos = 0
    def u(fmt):
        nonlocal pos
        v = struct.unpack_from('>' + fmt, data, pos); pos += struct.calcsize('>' + fmt); return v[0]
    def string():
        nonlocal pos
        n = u('H'); s = data[pos:pos + n].decode('utf-8'); pos += n; return s
    def payload(t):
        nonlocal pos
        if t == 1: return u('b')
        if t == 2: return u('h')
        if t == 3: return u('i')
        if t == 4: return u('q')
        if t == 5: return u('f')
        if t == 6: return u('d')
        if t == 7:
            n = u('i'); v = data[pos:pos + n]; pos += n; return v
        if t == 8: return string()
        if t == 9:
            it = u('b'); n = u('i'); return [payload(it) for _ in range(n)]
        if t == 10:
            d = {}
            while True:
                tt = u('b')
                if tt == 0: return d
                k = string(); d[k] = payload(tt)
        if t == 11:
            n = u('i'); v = list(struct.unpack_from('>%di' % n, data, pos)); pos += 4 * n; return v
        if t == 12:
            n = u('i'); v = list(struct.unpack_from('>%dq' % n, data, pos)); pos += 8 * n; return v
        raise ValueError(t)
    assert u('b') == 10; string()
    return payload(10)

def unpack(longs, bits, count):
    mask = (1 << bits) - 1
    big = 0
    for i, l in enumerate(longs): big |= (l & 0xFFFFFFFFFFFFFFFF) << (64 * i)
    return [(big >> (i * bits)) & mask for i in range(count)]

def load(path):
    root = read_nbt(gzip.open(path).read())
    out = {}
    for name, reg in root['Regions'].items():
        sx, sy, sz = (reg['Size'][k] for k in 'xyz'); px, py, pz = (reg['Position'][k] for k in 'xyz')
        ax, ay, az = abs(sx), abs(sy), abs(sz)
        pal = []
        for p in reg['BlockStatePalette']:
            props = p.get('Properties', {})
            pal.append(p['Name'] + ('[' + ','.join(f'{k}={v}' for k, v in sorted(props.items())) + ']' if props else ''))
        bits = max(2, (len(pal) - 1).bit_length())
        idx = unpack(reg['BlockStates'], bits, ax * ay * az)
        for i, v in enumerate(idx):
            if pal[v] == 'minecraft:air': continue
            x = i % ax; z = (i // ax) % az; y = i // (ax * az)
            out[(x, y, z)] = pal[v]
        out['_tes'] = {(t['x'], t['y'], t['z']): t for t in reg.get('TileEntities', [])}
        out['_te'] = len(out['_tes'])
        out['_size'] = (sx, sy, sz)
    return out

if __name__ == '__main__':
    for f in sorted(glob.glob(sys.argv[1] + '/*.litematic')):
        b = load(f)
        print(os.path.basename(f), b['_size'], 'TE', b['_te'])
        from collections import Counter
        c = Counter(v.split('[')[0] for k, v in b.items() if isinstance(k, tuple))
        print('  ', dict(c))
