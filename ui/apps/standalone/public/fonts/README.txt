FOCUS bundled reading fonts

Source Han Serif (Adobe, version 2.003)
https://github.com/adobe-fonts/source-han-serif/tree/release
License: SourceHanSerif-LICENSE.txt (SIL OFL 1.1)

Source Han Sans (Adobe, version 2.005)
https://github.com/adobe-fonts/source-han-sans/tree/release
License: SourceHanSans-LICENSE.txt (SIL OFL 1.1)

LXGW Neo ZhiSong Screen (release 26.08.21)
https://github.com/lxgw/LxgwNeoXiZhi-Screen/releases/tag/26.08.21
License: NeoZhiSong-IPA-LICENSE.txt (IPA Font License 1.0)
Additional notices: NeoZhiSong-other-LICENSES.txt
The original, unmodified TTF is included as neo-zhisong-screen.ttf.

Restore the original IPA font:
Download and install IPAex Mincho or IPAmj Mincho from the original publishers:
https://moji.or.jp/ipafont/ipafontdownload/
https://moji.or.jp/mojikiban/ipamjfont/
Restart the browser, then select the Neo ZhiSong Screen option in Settings.
Its CSS uses local("IPAexMincho"), then local("IPAmjMincho"), before the
bundled derived font. Uninstall those originals to return to the bundled font.
The original IPA fonts use Japanese character forms.

The Adobe files are losslessly converted from upstream OTF to WOFF2 using
fontTools. Glyph outlines and character mappings are not edited.
manifest.json records upstream versions, source hashes and output hashes.
