#!/usr/bin/env bash
# Download open real-world drone media samples for the media extractor tests.
#
# Sources (public GitHub repositories; check each repository's licence
# before redistributing the files - they are downloaded, not bundled):
#   * OpenDroneMap sample datasets (github.com/OpenDroneMap/odm_data_*):
#     DJI Phantom 3 (FC300X), Autel EVO II (XT705), senseFly eBee payloads
#     (Canon S110, Canon ELPH 300, Sony WX220), and plain cameras.
#   * DJI_SRT_Parser samples (github.com/JuanIrache/DJI_SRT_Parser/samples):
#     .SRT telemetry from 18 DJI models plus deliberately broken files.
#
# Every file is verified against the SHA-256 recorded when the tests were written.
set -euo pipefail
DEST="${1:-tests/fixtures/media_samples}"
mkdir -p "$DEST/odm" "$DEST/srt"

ODM=(
  "toledo master images/1JI_0062.JPG toledo_1JI_0062.JPG"
  "bellus master images/IMG_1297_RGB.jpg bellus_IMG_1297_RGB.jpg"
  "helenenschacht main images/MAX_0002.JPG helenenschacht_MAX_0002.JPG"
  "zoo master images/DSC01605.JPG zoo_DSC01605.JPG"
  "seneca master images/IMG_0446.jpg seneca_IMG_0446.jpg"
  "caliterra master images/IMG_9354.jpg caliterra_IMG_9354.jpg"
  "copr master images/IMG_0022.jpg copr_IMG_0022.jpg"
  "langley master images/IMG_0525.jpg langley_IMG_0525.jpg"
)
for entry in "${ODM[@]}"; do
  read -r repo branch path name <<< "$entry"
  [ -f "$DEST/odm/$name" ] || curl -fsSL -o "$DEST/odm/$name" \
    "https://raw.githubusercontent.com/OpenDroneMap/odm_data_${repo}/${branch}/${path}"
done

SRT=(MAVIC3.srt Mini_SE.SRT air2s.srt broken_empty.SRT broken_empty2.SRT broken_incomplete.SRT
     broken_incomplete2.SRT m2zoom.SRT matrice_300.srt mavic_2_style.SRT mavic_2pro_new.SRT
     mavic_air.SRT mavic_air2.srt mavic_mini.SRT mavic_pro.SRT mavic_pro_buggy.SRT
     mix_p4rtk_mavic2pro.srt old_format.SRT p4_rtk.SRT p4p_sample.SRT)
for name in "${SRT[@]}"; do
  [ -f "$DEST/srt/$name" ] || curl -fsSL -o "$DEST/srt/$name" \
    "https://raw.githubusercontent.com/JuanIrache/DJI_SRT_Parser/master/samples/${name}"
done

(cd "$DEST/odm" && sha256sum -c --quiet <<'EOF'
e76e5131257052ec7d909be1b68bd5a8214f5ed7b4bb98c9291b93ed44ebdadb  bellus_IMG_1297_RGB.jpg
5dc04e4bad47bb8063f737227291f1091a625fa0ef3e9f03791503ef453dbed3  caliterra_IMG_9354.jpg
99bd46ffed64c390be4f0dfb42bfba57c492f28e931475e6e12d81d67fdfe0f9  copr_IMG_0022.jpg
7342e91866f2673ccab1eb7df62b14de91ff395c86ac9545e2c570bf8598f752  helenenschacht_MAX_0002.JPG
d811e952cab0fbe6922101dfc0bc4bebb0f88666c3b02cee9d8b71cdc4a7df23  langley_IMG_0525.jpg
35cd671185944bcbcab24d915e6af0ea02a45c1acd21e874349d2d338c4c2bf4  seneca_IMG_0446.jpg
91d679d321e50da2d862394040000bdb022ac1a0dc04e67fe61c9c19936359a0  toledo_1JI_0062.JPG
0bddd527c53505f10d22b18cac209c05dc7951ea6de57a62225daaa5c83fd029  zoo_DSC01605.JPG
EOF
)
(cd "$DEST/srt" && sha256sum -c --quiet <<'EOF'
2e5945b7d9bce51568bde5cc6576bb3dcc4362cebe20a3a8588260cb82cdef23  MAVIC3.srt
19194a43faf294d9e430fdaa44c9d308e0c952f7bf4a49c457659b26724d3d33  Mini_SE.SRT
f43cf00992c26cc58a401378231134164b1b37c178179e6c8889f82965911569  air2s.srt
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  broken_empty.SRT
4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865  broken_empty2.SRT
0798bf96bf014634b79f6b3d9cd0a4f6864010cc46b09b053766407d70b7377e  broken_incomplete.SRT
6ebaf66ee41d38340a1f8eb93e5ec152edcf879fc3a8be2dc58e311dfc75537e  broken_incomplete2.SRT
1b5ead2b40975bb9f0e816c4320850a5d12f853a624a9c432fd253d14361a6a9  m2zoom.SRT
503f42e373b6c5edb0edf1bf2e03491e30af37bd98142a3499ece4c83d0fd9f9  matrice_300.srt
4974a929c8f64d3efb36178b9abf325542351d2c92f4979269dd1988da001d4d  mavic_2_style.SRT
7a0175271c11b9ca78fa400409bfada018207290acbaf5960c47176e009af188  mavic_2pro_new.SRT
972812dcb91a5ccc86fdd7542c8bc0711054de3ae23a2ee1c81067475e16486a  mavic_air.SRT
f57fbd7303068f4fbcd4da2cd7d46a4c14ee873b2640f5ed08f8a7271a081571  mavic_air2.srt
7ead21808d8dcdcfba01167838719b2e2d5b98b4c6150ed34302a1c859c94033  mavic_mini.SRT
cb74783a412f6bbd195d02b324b6674c36a5066ca1aee058302650b7beba4abf  mavic_pro.SRT
75708165c627400d11c4301d4728afd18ccef2f29da46d0faaf6bef84c8779e3  mavic_pro_buggy.SRT
5678c5a1b11b4ad6966ddcd5c9396bd655af5112c59fd65969403730e59ab0fc  mix_p4rtk_mavic2pro.srt
367d7d360383532a4c141e57037d00a09f3ab48fce04beae0c3b1adce2a191b9  old_format.SRT
c8273a746207ed93995a9df625ec5ee4c668c9ea9e392ab20619000cbed8fe9f  p4_rtk.SRT
b52b7664efc5a02ce60a0d0733c964a1278f35e5fe3df69669673123dde810d3  p4p_sample.SRT
EOF
)
echo "Samples ready in $DEST (hashes verified)"
echo "Run:  MEDIA_SAMPLES_DIR=$DEST pytest -q tests/media"
