import re, sys, zipfile

class BadFile(Exception): pass

UNICODE_STRING_REGEX = r'UnicodeString="(.+)"'

MOVE_REGEX = r'([A-Z],[ \d]\d)'

OTHER_MOVE_REGEX = r'([A-Z],[ \d]\d)(.*)$'              # needs to be run on only the latter part of the string, else it will get 1st move

SITUATION_REGEX = r'(0\.\d\d\d\d)'

HOTSPOT_DELTA = 0.04    # Hotspot (sgf: "HO[1]") if delta >= this


def sgf_point_from_english_string(s, boardsize):        # C17 ---> cc
    if len(s) not in [2,3]:
        return None
    s = s.upper()
    xlookup = " ABCDEFGHJKLMNOPQRSTUVWXYZ"
    try:
        x = xlookup.index(s[0])
    except:
        return None
    try:
        y = boardsize - int(s[1:]) + 1
    except:
        return None
    if 1 <= x <= boardsize and 1 <= y <= boardsize:
        pass
    else:
        return None

    if x < 1 or x > 26 or y < 1 or y > 26:
        return None
    s = ""
    s += chr(x + 96)
    s += chr(y + 96)
    return s


def sgf_point_from_point(x, y):                            # 3, 3 --> "cc"
    if x < 1 or x > 26 or y < 1 or y > 26:
        return None
    s = ""
    s += chr(x + 96)
    s += chr(y + 96)
    return s


def handicap_points(boardsize, handicap, tygem = False):

    points = set()

    if boardsize < 4:
        return points

    if handicap > 9:
        handicap = 9

    if boardsize < 13:
        d = 2
    else:
        d = 3

    if handicap >= 2:
        points.add((boardsize - d, 1 + d))
        points.add((1 + d, boardsize - d))

    # Experiments suggest Tygem puts its 3rd handicap stone in the top left

    if handicap >= 3:
        if tygem:
            points.add((1 + d, 1 + d))
        else:
            points.add((boardsize - d, boardsize - d))

    if handicap >= 4:
        if tygem:
            points.add((boardsize - d, boardsize - d))
        else:
            points.add((1 + d, 1 + d))

    if boardsize % 2 == 0:      # No handicap > 4 on even sided boards
        return points

    mid = (boardsize + 1) // 2

    if handicap in [5, 7, 9]:
        points.add((mid, mid))

    if handicap >= 6:
        points.add((1 + d, mid))
        points.add((boardsize - d, mid))

    if handicap >= 8:
        points.add((mid, 1 + d))
        points.add((mid, boardsize - d))

    return points


def get_metadata(strings):
    metadata = dict()

    for s in strings:
        if s.startswith("Black: "):
            metadata["PB"] = s[7:]
        if s.startswith("White: "):
            metadata["PW"] = s[7:]
        if s.startswith("Komi: "):
            try:
                metadata["KM"] = float(s[6:])
            except:
                pass
        if s.startswith("Handicap Stones: "):
            try:
                metadata["HA"] = int(s[17:])
            except:
                pass

        if len(s) == 10 and s[4] == "/" and s[7] == "/":
            metadata["DT"] = "{}-{}-{}".format(s[0:4], s[5:7], s[8:10])

    metadata["GM"] = 1
    metadata["FF"] = 4
    return metadata


def main():
    if len(sys.argv) < 2:
        print("Usage: {0} <filename>".format(sys.argv[0]))
        print("The filename should be a OXPS file from CrazyStone's Print command")
        exit()

    for zfile in sys.argv[1:]:

        with zipfile.ZipFile(zfile) as arch:

            pages = []

            n = 1
            while True:
                try:
                    decompressed_page = arch.open("Documents/1/Pages/{}.fpage".format(n))
                    pages.append(decompressed_page)
                except:
                    break
                n += 1

            if len(pages) == 0:
                raise BadFile

            lines = []

            for page in pages:
                for line in page:
                    lines.append(line)

            strings = []

            for line in lines:
                extract = re.search(UNICODE_STRING_REGEX, str(line))
                if extract:
                    strings.append(extract.group(1))

            metadata = get_metadata(strings)

            goodstrings = []

            nextstart = 1
            for s in strings:
                startstring = "{} ".format(nextstart)
                if s.startswith(startstring):
                    goodstrings.append(s)
                    nextstart += 1

            sgf = "(;"
            colour = "B"

            for key in metadata:
                sgf += key + "[" + str(metadata[key]) + "]"

            if metadata.get("HA"):
                colour = "W"
                points = handicap_points(19, metadata["HA"])
                sgf += "AB"
                for point in points:
                    sgf += "[{}]".format(sgf_point_from_point(point[0], point[1]))
                sgf += "C[WARNING: Handicap placement has been guessed at by csa2sgf.py]"

            for s in goodstrings:

                # First REGEX

                extract = re.search(MOVE_REGEX, s)
                if extract:

                    # i.e. there actually is a move

                    actual_move = extract.group(1)
                    letter = actual_move[0]
                    number = int(actual_move[2:])
                    sgf_move = sgf_point_from_english_string("{}{}".format(letter, number), 19)     # FIXME: currently assuming 19x19

                    sgf += ";{}[{}]".format(colour, sgf_move)
                    comment = ""

                    colour = "B" if colour == "W" else "W"          # This is for the next move after this one

                    # Second REGEX

                    extract = re.search(OTHER_MOVE_REGEX, s[8:])    # Don't start at start so as not to get the first move
                    if extract:
                        better_move = extract.group(1)
                        letter = better_move[0]
                        number = int(better_move[2:])
                        sgf_move = sgf_point_from_english_string("{}{}".format(letter, number), 19) # FIXME: currently assuming 19x19

                        sgf += "TR[{}]".format(sgf_move)

                        delta = extract.group(2)

                        if better_move != actual_move:
                            comment += "CS prefers {}{}".format(letter, number)
                            try:
                                delta_float = float(delta)
                                comment += " -- delta: {:.2f} %\n".format(delta_float * 100)
                                if delta_float >= HOTSPOT_DELTA:
                                    sgf += "HO[1]"
                            except:
                                comment += "\n"

                    # Third REGEX

                    extract = re.search(SITUATION_REGEX, s)
                    if extract:
                        situation_float = float(extract.group(1))
                        comment += "Black winrate: {:.2f} %\n".format(situation_float * 100)

                    # Done

                    if comment:
                        comment = comment.strip()
                        sgf += "C[{}]".format(comment)

            sgf += ")"

            outfilename = "{}_analysis.sgf".format(zfile)

            with open(outfilename, "w") as outfile:
                outfile.write(sgf)



main()
