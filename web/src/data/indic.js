/**
 * Kannada, Hindi and Tamil as they actually appear on the record —
 * the masthead, the words a household used, the printing on a form.
 *
 * These are artifacts, not a translation layer. Lakshmi did not
 * report her tap in English, and the form she was handed was not
 * printed in one language either.
 */

export const MASTHEAD = {
  kn: 'ಪಂಚಾಯತ್',
  hi: 'पंचायत',
  en: 'Panchayat',
}

/** What she said, on the third morning. */
export const REPORT = {
  kn: 'ಮೂರು ದಿನದಿಂದ ನೀರು ಬಂದಿಲ್ಲ. ಟ್ಯಾಂಕ್ ಖಾಲಿ ಇದೆ.',
  gloss: 'Three days, no water has come. The tank is empty.',
  by: 'Lakshmi · 12/12 · voice note, 05:40',
}

/** The same fault, reported by the street in three scripts. */
export const VOICES = [
  {
    script: 'kn',
    tag: 'ಕನ್ನಡ',
    text: 'ಮೋಟಾರ್ ಒಣಗಿ ಓಡುತ್ತಿದೆ. ಭಾನುವಾರದಿಂದ ಲೈನ್‌ನಲ್ಲಿ ಏನೂ ಇಲ್ಲ.',
    gloss: 'The motor runs dry. Nothing in the line since Sunday.',
    house: '12/09',
  },
  {
    script: 'ta',
    tag: 'தமிழ்',
    text: 'மீண்டும் டேங்கர் வரவழைத்தோம். இந்த வாரம் மூன்றாவது.',
    gloss: 'Ordered a tanker again. Third one this week.',
    house: '12/17',
  },
  {
    script: 'hi',
    tag: 'हिन्दी',
    text: 'हमारे यहाँ पानी आ रहा है। लाइन अलग है।',
    gloss: 'We have water here. Our line is a different one.',
    house: '12/11',
  },
]

/** Printing on the grievance form, as issued. */
export const FORM = {
  title: { kn: 'ದೂರು ಅರ್ಜಿ', hi: 'शिकायत प्रपत्र', en: 'Grievance Application' },
  ward: { kn: 'ವಾರ್ಡ್ ೧೨', hi: 'वार्ड १२', en: 'Ward 12' },
  fields: [
    { kn: 'ಅರ್ಜಿದಾರರ ಹೆಸರು', en: 'Name of applicant' },
    { kn: 'ವಿಳಾಸ', en: 'Address' },
    { kn: 'ದೂರಿನ ವಿವರ', en: 'Particulars of grievance' },
    { kn: 'ಸಹಿ', en: 'Signature' },
  ],
  footer: {
    kn: 'ಸಕಾಲ ಸೇವೆಗಳ ಅಧಿನಿಯಮ, ೨೦೧೧',
    en: 'Karnataka Sakala Services Act, 2011',
  },
}

/** What the desk stamped on it. */
export const STAMP_TEXT = {
  en: 'RESOLVED',
  kn: 'ಇತ್ಯರ್ಥವಾಗಿದೆ',
}
