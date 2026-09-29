"""
Cursed Horoscope — Halloween-themed sticky panel mini-game.
Persistent sticky panel with 12 zodiac buttons. One random cursed prediction
per click. Response stays in the channel; panel is always reposted last.
Follows the same architecture as Nazar Speaks / The Love Professor.
"""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.storage import load_json, save_json

logger = logging.getLogger("bovary_bot.cursedhoroscope")

# ---------------------------------------------------------------------------
# Config — SET YOUR CHANNEL ID HERE
# ---------------------------------------------------------------------------
GIF_URL = "https://ik.imagekit.io/BassaniStudios/madame%20boavry.gif?updatedAt=1790644003965"
# TODO: replace with the real channel ID where this panel will live
ALLOWED_CHANNEL_ID = 1554302868293554196
COOLDOWN_SECONDS = 600  # 10 minutes
PANEL_STATE_FILE = "cursedhoroscope_panel.json"

# Dark cursed / Halloween theme
CURSED_PURPLE = discord.Color.from_rgb(48, 8, 48)
CURSED_RED = discord.Color.from_rgb(160, 20, 40)
CURSED_GOLD = discord.Color.from_rgb(180, 140, 40)
CURSED_BLACK = discord.Color.from_rgb(20, 8, 20)

# ---------------------------------------------------------------------------
# Zodiac data + cursed predictions (English)
# Each list is the merged + translated content from both Portuguese sets.
# One random phrase is chosen on every click.
# ---------------------------------------------------------------------------
SIGNS = {
    "aries": {
        "name": "Aries",
        "emoji": "♈",
        "title": "🔥 THE IMPULSIVE DEMON",
        "phrases": [
            "🎃 Today you will make a decision so bad even the devil will ask you to think it over.",
            "☠️ Your guardian angel quit. Reason: repeated offenses.",
            "🍺 Tomorrow’s hangover will be your true summoning ritual.",
            "💸 Your money will vanish. It wasn’t theft. It was supernatural financial incompetence.",
            "💀 Today you will spend as if you had seven lives. Your bank disagrees.",
            "💔 Your ex will appear like a ghost from the past. Unlike a ghost, they still have WhatsApp.",
            "🔥 You will flirt with someone who clearly carries problem energy. Naturally, you will proceed.",
            "🪦 Your love life is so dead the cemetery asked you to stop visiting.",
            "🤡 Today you will be publicly humiliated. At least there will be witnesses.",
            "🍺 “Just one more” will be the last words spoken before the disaster.",
            "💀 Your dignity will die today. The funeral is tomorrow, along with your hangover.",
            "🎃 The universe prepared a surprise. You are the gift.",
            "🔥 Your libido will be alive. Your common sense will be in decomposition.",
            "💸 Today you will discover that a credit card also works as a torture instrument.",
            "👻 Someone from the past will return. Not even hell can get rid of you.",
            "☠️ Your luck died overnight. Nobody knows where they buried it.",
            "🤡 You will try to impress someone and end up providing material for the next gossip.",
            "🍺 Today you will drink as if there is no tomorrow. Your liver is hoping there really isn’t.",
            "🪦 Your relationship has corpse energy: cold, motionless, and nobody knows why it’s still there.",
            "🎃 You will hear “trust me”. Run.",
            "💀 Today your greatest enemy will be your own decision-making ability.",
            "🔥 A hot night is predicted. The problem will be explaining it to whom.",
            "💸 Your paycheck will arrive like a ghost: appear and disappear immediately.",
            "👻 Today you will be haunted by a choice you could have avoided.",
            "🤡 Your shame will be so great even your phone will want to delete the evidence.",
            "☠️ Hell opened a vacancy for you. Your résumé impressed them.",
            "🍺 Your body will ask for water. You will offer alcohol. Toxic relationship.",
            "🪦 Today you will discover that some people should stay buried. Including certain conversations.",
            "🎃 The moon is full. Your brain is also full of bad decisions.",
            "💀 Aries, today you don’t need to fear the monsters. You are perfectly capable of creating your own.",
            "Presságio: someone will say “stay calm”. Don’t.",
            "Your sign is in an excellent phase for irreversible decisions for completely idiotic reasons.",
            "The Moon entered Aries. Common sense left through the window.",
            "Astral alert: alcohol, messages and pride should not be combined. You will combine all three.",
            "An opportunity will appear. Unfortunately you will recognize it as a challenge.",
            "The stars recommend patience. You will interpret it as a provocation.",
            "There is a small chance you leave tonight unscathed. Don’t bet money on it.",
            "Your energy is high. Your ability to evaluate consequences is missing.",
            "Good news: nobody will forget what you do today. Bad news: nobody should.",
            "The constellation of Aries predicts an unnecessary expense with absolute conviction.",
            "Your romantic future contains fire. It also contains fire extinguishers.",
            "An attractive person will appear. The brain will ask for caution. The rest of the body will hold a meeting without it.",
            "Your name will be mentioned in a conversation. You won’t like the context.",
            "Financial horoscope: your money didn’t die. It is simply missing under suspicious circumstances.",
            "The corpse of your dignity has not yet been identified.",
            "The night promises fun, alcohol and decisions that will need an imaginary lawyer.",
            "You are one sentence away from turning a normal conversation into a historic event.",
            "An old rivalry may resurrect. Do not feed the zombie.",
            "Destiny offers two options: prudence or a funny story. You already chose.",
            "Your sign recommends distance from people who start sentences with “I had an idea”.",
            "The problem is that you will be that person.",
            "There is a strange energy in the air. There is also tequila.",
            "An emotional debt will be collected with interest.",
            "The full moon will illuminate exactly what you were trying to hide.",
            "Your guardian angel is not missing. He is hiding behind a tree.",
            "The forecast for the early hours: terrible choices with a great soundtrack.",
            "Your patience will suffer sudden death.",
            "The wake will be tomorrow, together with your hangover.",
            "The stars do not say you are screwed. Their silence is more worrying.",
            "Celestial verdict: you remain the main person responsible for your own chaos.",
        ],
    },
    "taurus": {
        "name": "Taurus",
        "emoji": "♉",
        "title": "💰 THE DEMON OF THE BILL",
        "phrases": [
            "🎃 Your money will be possessed by an entity called “unexpected expenses”.",
            "💸 Today your bank balance will look like a tombstone.",
            "☠️ The bill will arrive. Hope will leave.",
            "🍺 You will drink to forget the bills. The bills will still be there tomorrow.",
            "💀 Your liver is considering a contractual termination.",
            "🪦 Your wallet is officially in a state of decomposition.",
            "💔 Your ex will reappear. Not even death can make that relationship rest in peace.",
            "🎃 You will go back to someone who already proved to be a terrible idea. The spirit of repetition is satisfied.",
            "🔥 Today someone will desire you. You will desire the wrong person.",
            "🤡 Your attempt at seduction will end looking like a police report.",
            "🍺 The hangover will be so brutal you will see your ancestors.",
            "💸 Today you will buy something useless and call it “a gift for myself”.",
            "☠️ Your credit card will be the true villain of this Halloween.",
            "👻 The ghost of consumerism is inside your wallet.",
            "🪦 Your relationship is dead, but nobody had the courage to unplug the machines.",
            "💀 Today you will discover that insistence does not turn shit into gold.",
            "🎃 A terrifying financial decision is approaching.",
            "🤡 You will be caught doing something you swore you would never do.",
            "🔥 Your sex life may improve today. Your ability to choose someone will not.",
            "💔 Someone will break your heart. Your history suggests you will thank them for the experience.",
            "🍺 Today you will have a hangover before even going to sleep.",
            "☠️ The universe wants you to save money. You will interpret it as a challenge.",
            "💸 Your salary was last seen fleeing desperately.",
            "👻 An old debt will return from the grave.",
            "🤡 Today you will be the clown of your own story.",
            "🪦 Your monthly budget will be buried without ceremony.",
            "🎃 Destiny says you will have luck. It did not specify in what.",
            "💀 Today even your couch will have more social life than you.",
            "🔥 Your desire will speak louder than your brain.",
            "☠️ Taurus, your financial stability is dead. Please do not try to resurrect it.",
            "Your sign entered the financial house. Your money ran out the back door.",
            "The entity that possesses your wallet answers to the name “impulse purchase”.",
            "There is a great financial opportunity in your path. It belongs to someone else.",
            "Omen: you will find something you want to buy. You didn’t need it.",
            "Your card is emotionally exhausted.",
            "The Moon is aligned with a charge you completely forgot about.",
            "Your financial situation is so dark even the accountant lit a candle.",
            "An irresistible promotion is approaching. Resist. You won’t.",
            "Your salary will have a brief passage through your account.",
            "The money will arrive at 09:00 and be declared dead at 09:07.",
            "There is a person from the past circling your thoughts. Maybe it’s longing. Maybe it’s lack of judgment.",
            "Your relationship is asking for stability. You will offer pizza.",
            "A romantic night may happen. The bill will be split.",
            "Alert: do not shop after midnight. Your nighttime self is financially possessed.",
            "The ghost of your ex still has emotional access to your brain.",
            "The good news is you will not be scammed today. The bad news is you will do it yourself.",
            "Your sex life is receiving influence from Mars. Your choice sense is receiving influence from Mercury retrograde.",
            "The result promises to be statistically worrying.",
            "A friend will ask to borrow money. The money will never be seen again.",
            "You also won’t see the friend.",
            "The constellation of Taurus recommends water, rest and distance from delivery apps.",
            "The cemetery of your wallet is getting crowded.",
            "Romantic forecast: strong attraction, questionable compatibility, excellent consequences for gossip.",
            "An old shame will return to collect rent.",
            "Your emotional stability is under maintenance.",
            "Do not try to resurrect dead relationships. They bite.",
            "The night has potential to end in a kiss or an emotional police report.",
            "Your luck is alive. Very weak, but alive.",
            "The universe asked for moderation. You interpreted it as decoration.",
            "Diagnosis: financially alive, emotionally questionable, spiritually in battery-saving mode.",
        ],
    },
    "gemini": {
        "name": "Gemini",
        "emoji": "♊",
        "title": "👻 THE TWO-FACED SPIRIT",
        "phrases": [
            "🎃 Today you will tell a lie and forget who you told it to.",
            "💀 Two versions of the story will leave your mouth. The corpse of the truth will stay in the middle.",
            "📱 A message sent today may haunt you for the rest of the month.",
            "🍺 You will drink and unlock someone who should have remained buried.",
            "💔 Your ex will receive a message. Hell will receive another.",
            "🤡 Today you will be caught in a contradiction so ridiculous even the ghost of shame will laugh.",
            "💸 Your money will disappear faster than a soul in purgatory.",
            "☠️ The bank no longer believes in you.",
            "🔥 Your libido will make decisions without consulting the board of directors.",
            "🪦 Your love life has so many undead it looks like an apocalypse.",
            "👻 Today you will be haunted by a conversation that should have ended with “good night”.",
            "🍺 The hangover will reveal information you didn’t want to know about yourself.",
            "💀 Your phone will be found with enough evidence to socially condemn you.",
            "🎃 You will flirt with someone. Afterwards you will discover why nobody else was flirting.",
            "🤡 Your dignity will be found on the floor of some place you don’t remember.",
            "💸 Today you will spend money on something you will call “necessary” while lying to yourself.",
            "☠️ Your guardian angel no longer knows which version of you to protect.",
            "💔 An old passion will return like a recurring curse.",
            "🔥 Desire will be strong. Regret will be stronger.",
            "🪦 Your common sense died at 11:47 p.m.",
            "👻 You will see a sign. You will ignore it. The devil will take notes.",
            "🍺 Today the drink will be liquid. The regret, solid.",
            "🤡 You will be the reason for laughter. At least someone is having fun.",
            "💀 Your karma found your address.",
            "🎃 Today you will have a terrible idea and convince someone to join.",
            "💸 The money will vanish. The witnesses will be your delivery apps.",
            "🪦 A relationship will be buried. You will try to dig it back up.",
            "🔥 Today your charm will be working. Unfortunately, against you.",
            "☠️ The universe is not confused about you. It simply gave up understanding.",
            "👻 Gemini, even your own thoughts are wearing a disguise.",
            "There are two people inside you. Both have terrible ideas.",
            "A message will be sent. You will immediately wish to delete your own existence.",
            "The problem will not be lying. It will be remembering who you told it to.",
            "Omen: three people will know something you told one person.",
            "Your phone contains enough information to destroy your reputation.",
            "Fortunately, nobody has discovered where the charger is yet.",
            "The night favors gossip, bad decisions and screenshots.",
            "Your ex may appear. Your self-control will not.",
            "An innocent conversation will have an absolutely unnecessary ending.",
            "You are entering a period of great communication. Terrible news for everyone around you.",
            "Alert: do not send voice notes after 2 a.m.",
            "If you do, at least pray first.",
            "The Moon is full and so is your message history.",
            "Someone will ask “do you remember?”. You won’t. They will have proof.",
            "Your money is disappearing in small installments. The investigation points to you.",
            "Alcohol will reveal thoughts that should have stayed locked away.",
            "Your love life looks like a WhatsApp group without an admin.",
            "Everyone talks. Nobody knows who is in control.",
            "An old flirt will resurrect. Do not confuse necromancy with romance.",
            "Tomorrow’s shame is being prepared today.",
            "Good news: you will have company.",
            "Bad news: they will be an accomplice.",
            "The universe does not know which version of you will show up tonight.",
            "Your guardian angel doesn’t either.",
            "The forecast indicates an argument. You will have arguments for three.",
            "A secret will escape. Maybe it’s yours. Maybe someone else’s.",
            "Alcohol will not cause the problem. It will only remove the filter.",
            "The early hours promise a story that will start with “I can’t believe we did that”.",
            "Dawn will bring silence, water and regret.",
            "Diagnosis: socially functional, morally negotiable.",
        ],
    },
    "cancer": {
        "name": "Cancer",
        "emoji": "♋",
        "title": "🪦 THE GHOST OF THE EX",
        "phrases": [
            "🎃 Today you will remember someone who should be dead to you.",
            "💔 Your ex will appear in your thoughts. Pay the overdue rent.",
            "👻 The past is back. Blocking didn’t work because apparently hell has memory.",
            "🍺 You will drink and send an emotional message.",
            "📱 The person will take a screenshot before answering.",
            "💀 Your dignity will be found floating in the message history.",
            "🪦 Today you will emotionally visit a relationship that has already been buried.",
            "🤡 You will call neediness “missing them”.",
            "🔥 A dangerous attraction will appear. You will call it destiny.",
            "💔 Destiny will call it a terrible choice.",
            "💸 Today you will spend money trying to buy happiness.",
            "🎃 Spoiler: it was not on sale.",
            "🍺 Your hangover will be accompanied by an existential crisis.",
            "☠️ Your pillow knows more secrets than your friends.",
            "👻 You will be haunted by a conversation from three years ago.",
            "🤡 Today you will stalk someone and discover something you preferred not to know.",
            "🪦 Your emotional peace will be buried again.",
            "💀 You will say “I moved on”. The universe will laugh.",
            "🔥 Today someone will awaken your desire and destroy your judgment.",
            "🍺 Your liver will be the only truly faithful thing in your life.",
            "💔 Love is dead. But apparently you still haven’t received the notice.",
            "🎃 Today your anxiety will wear the costume of intuition.",
            "👻 You will see signs in everything. Including where absolutely nothing exists.",
            "🤡 Your shame will be public; your suffering will be private.",
            "💸 Your bank balance will match your emotional state perfectly.",
            "☠️ The universe recommends moving on. You will look back.",
            "🪦 Today there will be a funeral. It will be of your hope that that person will change.",
            "🔥 Your heart wants romance. Your history wants supervision.",
            "👻 An old memory will return to drink your last neuron.",
            "💀 Cancer, your past is dead. The problem is you keep bringing flowers.",
            "The past found your new address.",
            "Do not open the door.",
            "An old memory will appear without being invited.",
            "Your brain chose exactly that 2018 memory to ruin your night.",
            "Romantic omen: the corpse of your relationship is still moving.",
            "It is not a miracle. It is lack of blocking.",
            "You will feel longing for someone who should only cause allergy.",
            "The pillow will be your accomplice and your therapist.",
            "A short message will have the power to destroy an entire night.",
            "“Hey, stranger” is a phrase that should be banned by law.",
            "The Moon is in a favorable position for stalking and unfavorable for your peace.",
            "Your heart wants answers. Your history shows that answers never help.",
            "An old love may appear in a dream.",
            "Your subconscious clearly does not pay rent.",
            "Financial horoscope: buy nothing. Especially what you call “I deserve it”.",
            "The emotional hangover will be accompanied by a physical one.",
            "The ghost of regret will pay a visit.",
            "He knows your name.",
            "There is someone thinking about you.",
            "Probably because you left something at their place.",
            "Your love life smells like funeral flowers.",
            "And you keep bringing flowers.",
            "A sentimental decision will be made based on a song.",
            "Do not do that.",
            "Your heart is working. Judgment is not.",
            "Supernatural alert: avoid opening old conversations.",
            "The past does not want to come back. It only wants to check if you are still an idiot.",
            "The night will have a melancholic energy.",
            "Use it to drink water and not send messages.",
            "Diagnosis: emotionally alive, romantically haunted.",
        ],
    },
    "leo": {
        "name": "Leo",
        "emoji": "♌",
        "title": "🩸 THE KING OF THE CEMETERY",
        "phrases": [
            "🎃 Today nobody will look at you. Prepare the funeral of your ego.",
            "💀 You will be ignored. Yes, you.",
            "🤡 Your moment of humiliation will arrive on time.",
            "🔥 You will try to seduce someone and end up negotiating with your own pride.",
            "🍺 Your hangover will knock the crown off your head.",
            "💸 Your card will be sacrificed on the altar of luxury.",
            "🪦 Your bank balance will be buried in a shallow grave.",
            "💔 Your ex is living normally. Terrible news.",
            "👻 You will try to cause jealousy and cause pity instead.",
            "🎃 Today someone will reject you. The universe calls that character development.",
            "💀 Your ego will survive. Unfortunately.",
            "🤡 You will tell an incredible story. Nobody will believe it.",
            "🔥 Your sex life promises emotion. The police of common sense recommend caution.",
            "🍺 Today you will drink like a king and wake up like a corpse.",
            "💸 Your salary will disappear before your eyes.",
            "👻 The ghost of humility will come to collect rent.",
            "🪦 Today your pride will be buried with black flowers.",
            "💔 You will discover that being desired does not mean being loved.",
            "☠️ Your vanity will meet its greatest enemy: a front camera.",
            "🎃 The mirror will lie less than your friends.",
            "🤡 Today you will be the joke and not the storyteller.",
            "🍺 Your liver is preparing a revolt.",
            "💀 You will wake up with a story you would rather not remember.",
            "🔥 Desire will defeat common sense. Again.",
            "👻 Your guardian angel is tired of saving your reputation.",
            "💸 Today you will spend money to look richer than you are.",
            "🪦 Your ego needs a minute of silence.",
            "🎃 Leo’s star is shining. It’s a fire, not glamour.",
            "☠️ Today the universe will not be your stage. It will be your court.",
            "💀 Leo, even the cemetery has limited space for large egos.",
            "The kingdom is empty. Nobody is looking.",
            "You will continue being the protagonist inside your own head.",
            "The audience, however, was not notified.",
            "Today your ego will meet someone who is not impressed.",
            "It will be educational.",
            "A photo will look excellent. Nobody important will react.",
            "The Moon recommends humility. You will probably ignore it.",
            "Omen: someone will steal your attention.",
            "The crime will be personal.",
            "Your ex will appear happy on social media. The algorithm knows exactly what it is doing.",
            "You will pretend you don’t care.",
            "Your search history will tell another story.",
            "The night favors glamour, alcohol and expensive regrets.",
            "Your card is about to finance your self-esteem.",
            "An attractive person will smile at you.",
            "It means nothing.",
            "You will interpret it as destiny.",
            "Your pride will have an out-of-body experience.",
            "The humiliation will be elegant.",
            "The embarrassment will be unforgettable.",
            "Sexual forecast: intense chemistry, nonexistent emotional responsibility.",
            "Your ego will call it a conquest.",
            "Your heart will call it a mistake.",
            "Your friend will call it “I told you so”.",
            "The cemetery reserves a tombstone with your name.",
            "It is not a threat. It is decoration.",
            "Today you will discover that being attractive does not prevent stupid decisions.",
            "Your glow remains strong.",
            "Probably because something caught fire.",
            "Diagnosis: majestic, dramatic and dangerously convinced.",
        ],
    },
    "virgo": {
        "name": "Virgo",
        "emoji": "♍",
        "title": "🧪 THE DOCTOR OF CHAOS",
        "phrases": [
            "🎃 Today you will find an error. You committed it.",
            "💀 You will try to organize the disaster. The disaster will win.",
            "🪦 Your spreadsheet will not survive Halloween.",
            "🍺 You will drink and analyze your own hangover like a clinical case.",
            "💸 Your budget will die of natural causes: you.",
            "🤡 Today you will correct someone who did not ask.",
            "Hell thanks you for your contribution.",
            "💔 Your relationship needs help. You will create a table.",
            "🔥 Your sex life will receive a performance report.",
            "🎃 Result: “needs improvement”.",
            "👻 You will interpret a message as criminal evidence.",
            "💀 Today your anxiety will put on a lab coat.",
            "🍺 You will say “I won’t exaggerate”.",
            "Your liver will laugh.",
            "💸 Your card will be admitted to the financial ICU.",
            "🪦 Today the illusion of control will die.",
            "🤡 You will try to avoid one embarrassment and end up producing another.",
            "👻 Your perfectionism will be possessed.",
            "💔 You will choose someone emotionally complicated and call it compatibility analysis.",
            "🔥 Today desire will be irrational. Finally, something outside your planning.",
            "☠️ Your guardian angel will deliver a report: “unsustainable”.",
            "🎃 You will try to control destiny. Destiny will laugh out loud.",
            "💀 Today your plan A will die.",
            "Your plan B will be busy.",
            "🍺 Plan C will be drinking.",
            "💸 Your account will be a digital tombstone.",
            "🪦 Today you will bury one worry and dig up three.",
            "🤡 Your logic will be defeated by an attractive person.",
            "👻 You will see chaos coming and still try to catalog it.",
            "☠️ Virgo, today not even your obsession with control will be able to resurrect your peace.",
            "Chaos entered your house without knocking.",
            "You prepared a spreadsheet to fight it.",
            "Chaos won.",
            "A small error will destroy an entire operation.",
            "You will know exactly who the culprit was.",
            "Unfortunately, it was you.",
            "The Moon is in an excellent position for losing patience.",
            "Your perfectionism will have an identity crisis.",
            "Omen: someone will do something the wrong way.",
            "You will not be able to stay silent.",
            "The funeral of peace will happen immediately afterwards.",
            "Your love life will be analyzed like a business contract.",
            "The other person only wanted a kiss.",
            "You presented an audit.",
            "Today alcohol will be used as a relaxation tool.",
            "You will spend the hangover analyzing symptoms on Google.",
            "Your card will be used for a “strategic” purchase.",
            "It was not strategic.",
            "It was expensive shit.",
            "Your relationship may survive.",
            "Your need to be right maybe not.",
            "The universe offers free chaos.",
            "You will try to organize it.",
            "Spoiler: it doesn’t work.",
            "An attractive person will destroy your logic.",
            "You will hate that.",
            "Your guardian angel is filling out an incident form.",
            "The form has 14 pages.",
            "Today your control will be placed in a coma.",
            "Diagnosis: perfectly organized on the outside, arson on the inside.",
        ],
    },
    "libra": {
        "name": "Libra",
        "emoji": "♎",
        "title": "⚰️ THE ROMANTIC GRAVEDIGGER",
        "phrases": [
            "🎃 You will have two bad options and spend half an hour choosing.",
            "💀 Disaster will choose for you.",
            "💔 Your ex will return. You will consider it. The cemetery prepares the grave.",
            "🔥 You will fall in love with a terrible idea that has excellent looks.",
            "🍺 Today the drink will make decisions for you.",
            "💸 Your wallet will be sacrificed by indecision.",
            "🤡 You will try to please everyone and end up hating everyone.",
            "👻 Your love life is being haunted by unavailable people.",
            "🪦 The relationship is dead. You are still choosing the flowers.",
            "💀 Today someone will leave you on read.",
            "At least someone made a decision.",
            "🎃 You will see a red flag and think it matches the decoration.",
            "🔥 The chemistry will be excellent. The choice will be horrible.",
            "🍺 Your hangover will have two phases: denial and regret.",
            "💸 The salary will die slowly during the night.",
            "👻 You will be seduced by a person who should come with a danger warning.",
            "🤡 Your dignity will die trying to keep the peace.",
            "💔 Today your heart will receive a critical hit.",
            "🪦 The funeral will be elegant, just like you.",
            "☠️ Your common sense has been missing since 2019.",
            "🎃 Today you will say “let’s see”.",
            "Hell will say “already seen”.",
            "💀 You will choose beauty over stability.",
            "Naturally.",
            "🔥 Today someone attractive will destroy your week.",
            "💸 And probably your bank account.",
            "👻 Your guardian angel is tired of mediating your relationships.",
            "🤡 You are not indecisive. You are just outsourcing responsibility.",
            "🪦 Today your emotional peace will be buried discreetly.",
            "☠️ Libra, even the Grim Reaper is tired of waiting for you to decide.",
            "Destiny prepared two doors.",
            "You will stare at them until a third one appears.",
            "Your greatest enemy today will be the “maybe” button.",
            "A dead relationship will return for a vote.",
            "You will be the only voter.",
            "The Moon recommends cutting toxic people.",
            "You will ask for a second opinion.",
            "And a third.",
            "An attractive person will appear.",
            "Your intelligence will abandon the location.",
            "The chemistry will be excellent.",
            "The choice will be terrible.",
            "Financial omen: buy after thinking.",
            "You will not think.",
            "Your bank already knows.",
            "Today someone will ask “what are we?”.",
            "Your spirit will leave the body.",
            "The night favors short romances and long regrets.",
            "Your ex may appear as a paranormal entity.",
            "Do not make eye contact.",
            "You will see a red flag.",
            "You will compliment the color.",
            "Your dignity will die trying to maintain harmony.",
            "The wake will be silent.",
            "The problem is you will still be choosing the flowers.",
            "Good news: you will make a decision.",
            "Bad news: it was the worst of the two.",
            "Your luck is divided.",
            "Exactly like you.",
            "Diagnosis: too attractive for your own good and too indecisive to notice.",
        ],
    },
    "scorpio": {
        "name": "Scorpio",
        "emoji": "♏",
        "title": "🩸 THE REAPER",
        "phrases": [
            "🎃 Today you will discover a truth and pretend you didn’t know.",
            "💀 Someone will lie to you. Terrible choice.",
            "👻 You will keep the information until the perfect moment.",
            "🪦 Your revenge will have a scheduled time.",
            "🔥 Today you will meet someone who will awaken desires and problems in equal measure.",
            "🍺 You will drink and unlock a person who should remain buried.",
            "💸 Your money will be spent on something questionable and absolutely necessary in that moment.",
            "💔 Your ex will reappear. Hell returned the package.",
            "🤡 Today someone will try to manipulate you.",
            "You will notice before the second sentence.",
            "👻 Your sixth sense will work perfectly.",
            "You will ignore it just to confirm.",
            "💀 Today someone will die emotionally in your presence.",
            "🪦 The relationship will be buried without a mass.",
            "🔥 Your libido will be in demonic mode.",
            "🍺 Your liver will ask for mercy. You will negotiate.",
            "💸 Your card will be used in the name of chaos.",
            "🎃 You will investigate someone and discover a true collection of red flags.",
            "🤡 Even so, you will remain curious.",
            "👻 Today you will scare someone just by looking.",
            "💀 Your mood will be so dark the cemetery will look optimistic.",
            "🪦 You do not hold grudges. You keep a dead archive.",
            "🔥 Today your gaze will cause more damage than your words.",
            "🍺 An apparently quiet night will end with questionable decisions.",
            "💔 Your heart is armored. Your curiosity is not.",
            "🎃 Karma will arrive dressed as an ex.",
            "💸 Revenge will be expensive.",
            "🤡 And still you will consider it money well spent.",
            "👻 Your guardian angel no longer interferes.",
            "☠️ Scorpio, today the monster under the bed is you.",
            "You already know who is lying.",
            "The problem is you also know the reason.",
            "Do nothing.",
            "Yet.",
            "Information will fall into your lap.",
            "Keep it.",
            "Observe.",
            "Wait.",
            "The person will make a mistake on their own.",
            "Your pleasure today will be discovering you were right.",
            "The Moon is favorable for secrets.",
            "And unfavorable for those who have secrets with you.",
            "Your ex may send a message.",
            "Hell apparently accepts returns.",
            "Attraction to someone dangerous will be particularly strong.",
            "Your instinct will say “no”.",
            "Your brain will ask “but what if?”.",
            "Disaster will thank you for participating.",
            "Your sex life has energy of a forbidden ritual.",
            "At least read the instructions.",
            "A friend will tell you gossip.",
            "You will pretend surprise.",
            "You already knew.",
            "Your mood will be darker than the cemetery.",
            "Your gaze will cause discomfort.",
            "Do not correct that.",
            "Today someone will discover they messed with the wrong person.",
            "You don’t need to do anything.",
            "Karma is working on a 12x36 scale.",
            "Diagnosis: dangerous, observant and emotionally archived.",
        ],
    },
    "sagittarius": {
        "name": "Sagittarius",
        "emoji": "♐",
        "title": "🍺 THE TOURIST OF HELL",
        "phrases": [
            "🎃 Today you will do something that will require witnesses.",
            "💀 You will call it an adventure.",
            "🍺 Your liver will call it a crime.",
            "💸 Your bank will call it fraud.",
            "🤡 Your friends will call it content.",
            "💔 Your ex will call it “I told you so”.",
            "🔥 You will flirt with someone you should avoid.",
            "Naturally, you will not avoid them.",
            "👻 Today you will accept an invitation without asking where it is.",
            "You will find out when it is too late.",
            "🪦 Your common sense will be buried before midnight.",
            "💀 You will say “trust me”.",
            "Nobody should.",
            "🍺 “Just one more” will be the beginning of the documentary.",
            "💸 Your card will finance your own investigation.",
            "🤡 You will be humiliated and call it a funny story.",
            "🔥 Your sex life will have an adventurous spirit.",
            "Your common sense will have the spirit of a corpse.",
            "👻 Today you will meet someone interesting.",
            "Unfortunately, too interesting.",
            "💔 The romance will last less than the hangover.",
            "🎃 Your guardian angel already brought a helmet.",
            "💀 You will do something stupid with confidence.",
            "Confidence will be the only admirable thing.",
            "🪦 Today your dignity will be buried in another ZIP code.",
            "💸 Your bank account will request asylum.",
            "🍺 Your liver will request independence.",
            "🤡 You will tell a story nobody should know.",
            "👻 Halloween ends. Your regret does not.",
            "☠️ Sagittarius, you are not lost. You are simply following the GPS of disaster.",
            "The universe put up a sign saying “no”.",
            "You will see it.",
            "You will go in anyway.",
            "An unexpected trip may happen.",
            "The problem will be discovering where you are.",
            "Your phone will have 2% battery.",
            "Your prudence will have 0%.",
            "Omen: someone will say “let’s do something crazy”.",
            "You will be that person.",
            "The drink will be abundant.",
            "Memory will be optional.",
            "Your card will be the first victim.",
            "Your liver will be the second.",
            "Your dignity will be the third.",
            "An ex may reappear.",
            "You will answer out of curiosity.",
            "Curiosity is like the devil: it never comes alone.",
            "An apparently normal night will end in a story.",
            "You will not be able to tell your mother.",
            "Nor your imaginary lawyer.",
            "Your love life will be spontaneous.",
            "And irresponsible.",
            "Your sign’s favorite combination.",
            "The guardian angel is wearing a helmet.",
            "Today someone will say “trust”.",
            "That person also doesn’t know what they are doing.",
            "You will find problems in new places.",
            "Spiritual tourism.",
            "Halloween matches your history perfectly.",
            "Diagnosis: adventurous by choice, disaster by vocation.",
        ],
    },
    "capricorn": {
        "name": "Capricorn",
        "emoji": "♑",
        "title": "🪦 THE CEO OF THE CEMETERY",
        "phrases": [
            "🎃 Today you will work while the dead rest.",
            "💀 Even a corpse has better work-life balance.",
            "💸 Your money will grow. Your responsibilities will too.",
            "🍺 You will drink to celebrate success.",
            "Tomorrow you will work to pay for the drink.",
            "💔 Your ex is living. You are producing.",
            "🔥 Someone will try to seduce you.",
            "You will ask for the résumé.",
            "🤡 Your sex life will be audited.",
            "Result: “insufficient activity”.",
            "🪦 Your rest died in 2018.",
            "👻 Today your work will haunt you even at home.",
            "💀 Your body will ask for vacation.",
            "You will answer with a meeting.",
            "💸 Your salary will arrive and be buried immediately.",
            "🎃 You are building a brilliant future.",
            "Pity you are not enjoying the present.",
            "🍺 Today your hangover will be considered an emergency meeting.",
            "💔 Your relationship ended because you answered “we’ll talk later”.",
            "“Later” never arrived.",
            "👻 Your guardian angel sent a collection email.",
            "🤡 You will try to turn a crisis into an opportunity.",
            "The crisis will turn you into a meme.",
            "🪦 Your funeral will have a corporate coffee break.",
            "💀 You will approve the budget.",
            "🔥 Today your greatest fantasy will be eight hours of sleep.",
            "💸 Your bank account will survive.",
            "Your soul will not.",
            "🎃 Hell offered a promotion.",
            "☠️ Capricorn, even the Reaper thinks you work too much.",
            "The office will be haunted.",
            "You will still be there.",
            "Even the dead know when it is time to leave.",
            "Your body asks for rest.",
            "You scheduled a meeting.",
            "Your love life entered business hours.",
            "Nobody showed up.",
            "Someone will try to seduce you.",
            "You will ask if that has tax consequences.",
            "Romance will die right there.",
            "Your salary will enter like a ghost.",
            "It will leave like a spirit.",
            "Your credit card is breathing on life support.",
            "You still consider buying something.",
            "Capitalism thanks you.",
            "The full moon will illuminate your schedule.",
            "There will be no empty space.",
            "You will call that productivity.",
            "The cemetery will call it burnout.",
            "Your ex is having fun.",
            "You are working.",
            "Each one with their choices.",
            "Today you will have an opportunity to rest.",
            "You will refuse it.",
            "Your funeral will be scheduled for the only free slot in your agenda.",
            "The decoration will be corporate.",
            "The coffee will be excellent.",
            "Your soul will keep working.",
            "Not even death ends your shift.",
            "Diagnosis: officially alive, professionally dead.",
        ],
    },
    "aquarius": {
        "name": "Aquarius",
        "emoji": "♒",
        "title": "👽 THE PHILOSOPHICAL CORPSE",
        "phrases": [
            "🎃 Today you will have an idea nobody asked for.",
            "💀 Nobody will understand.",
            "You also will not explain.",
            "👻 Your guardian angel asked for an instruction manual.",
            "🍺 You will have a philosophical revelation in the bathroom.",
            "Tomorrow you will not remember.",
            "💸 Your miraculous investment will be a financial funeral.",
            "💔 Your ex will try to come back.",
            "You will analyze it scientifically.",
            "🔥 Today you will meet someone emotionally stable.",
            "You will run as if you saw a demon.",
            "👻 You will meet someone problematic.",
            "You will become interested.",
            "🤡 Science cannot explain it.",
            "🪦 Your love life is in a state of decomposition.",
            "💀 Your brain has more theories than evidence.",
            "🎃 Today you will be misunderstood.",
            "Maybe because you are talking nonsense.",
            "🍺 Your hangover will be existential.",
            "💸 Your card will have an identity crisis.",
            "🔥 Your libido will present arguments your logic cannot refute.",
            "👻 Today you will disappear socially.",
            "Nobody will be surprised.",
            "🤡 You will be strange on purpose.",
            "Afterwards you will discover it was not necessary.",
            "🪦 Your common sense will be buried under abstract concepts.",
            "💀 You will try to explain your decision.",
            "Do not explain.",
            "🎃 The universe also does not understand.",
            "☠️ Aquarius, even the aliens decided not to abduct you today.",
            "Something inexplicable will happen.",
            "You will probably find it interesting.",
            "Normal people would call it a problem.",
            "You will call it an experience.",
            "Today an absurd theory will seem perfectly logical.",
            "Alcohol will help.",
            "Your brain will open 47 tabs.",
            "None will have an answer.",
            "Your ex will try to come back.",
            "You will do a sociological analysis before answering.",
            "The person will give up.",
            "Scientific result: relationship terminated.",
            "Your money will be invested in something nobody understands.",
            "Including you.",
            "The Moon is favorable for useless thoughts at 3 a.m.",
            "Your sleep will be sacrificed.",
            "An emotionally stable person will cross your path.",
            "You will immediately become suspicious.",
            "A problematic person will appear.",
            "You will become curious.",
            "Science does not explain everything.",
            "Your humor will be so dry the desert will be offended.",
            "Today you will disappear from the group.",
            "You will return three days later as if nothing happened.",
            "Your guardian angel gave up following the reasoning.",
            "Sex life will have experimental behavior.",
            "The laboratory recommends consent and common sense.",
            "Common sense did not show up.",
            "Your corpse would be hard to explain.",
            "Diagnosis: biologically human, operationally an anomaly.",
        ],
    },
    "pisces": {
        "name": "Pisces",
        "emoji": "♓",
        "title": "🧟 THE ROMANTIC UNDEAD",
        "phrases": [
            "🎃 Today you will fall in love with someone who needs an exorcism.",
            "💔 You will call it a connection.",
            "Everyone else will call it a problem.",
            "👻 Your ex will appear in your dreams.",
            "Your brain needs supervision.",
            "🍺 You will drink and write a message that looks like an emotional suicide note.",
            "Tomorrow you will delete it.",
            "The other person will already have a screenshot.",
            "💸 Your money will be spent trying to buy happiness.",
            "It was not available.",
            "🔥 Today you will desire someone completely inadequate.",
            "Your history will be satisfied.",
            "🪦 Your love life is technically dead.",
            "You will try to resurrect it.",
            "💀 Terrible idea.",
            "🤡 Today you will confuse neediness with destiny.",
            "👻 You will see signs where only coincidences exist.",
            "🎃 Even an “exit” sign will look like a message from the universe.",
            "🍺 Your hangover will be spiritual.",
            "💸 Your bank account will be emotionally supportive.",
            "💔 You will suffer for someone who is sleeping peacefully.",
            "🔥 Your heart wants romance.",
            "Your brain wants intervention.",
            "🪦 Today your guardian angel will pretend not to see.",
            "🤡 You will romanticize a red flag.",
            "It will look even more beautiful at night.",
            "💀 Your dignity will be found in an emotional cemetery.",
            "👻 You are not lost.",
            "You are sightseeing in your own disaster.",
            "☠️ Pisces, today even your dreams will ask you to stop being so needy.",
            "You will find a red flag and think it is beautiful.",
            "It is not romance. It is emotional necromancy.",
            "Someone will reply “lol”.",
            "You will create an entire love story.",
            "The other person doesn’t even know your last name.",
            "The Moon is favorable for illusions.",
            "You did not need that help.",
            "Your ex will appear in a dream.",
            "Your brain continues working against you.",
            "Today a song will destroy your emotional stability.",
            "You will listen to it again.",
            "Naturally.",
            "Your money will be spent on something sentimentally useless.",
            "At least it will have meaning.",
            "Financially, none.",
            "An improbable passion will appear.",
            "It will be improbable for excellent reasons.",
            "You will ignore all of them.",
            "Your love life smells like a wet cemetery.",
            "Still you will bring flowers.",
            "Alcohol will make your feelings more honest.",
            "Terrible idea.",
            "You will write a message.",
            "Delete it.",
            "Rewrite it.",
            "Send it.",
            "Regret it.",
            "The sequence is astrologically guaranteed.",
            "Your guardian angel will not interfere.",
            "Diagnosis: heart working, brain in ghost mode.",
        ],
    },
}

# Extra short prophecies that can be mixed in if desired (optional pool)
EXTRA_PROPHECIES = [
    "☠️ Today you will have luck. Unfortunately it will be the luck of finding money and spending it the same day.",
    "🎃 The universe prepared a surprise. You are the victim.",
    "👻 Your guardian angel is behind you. Not to protect. To witness.",
    "🪦 Today something will die. We hope it is only your dignity.",
    "💀 Destiny opened a door. Probably the wrong one.",
    "🍺 Today you will drink as if tomorrow does not exist. Tomorrow will exist. So will the hangover.",
    "💸 Your bank balance is already using corpse makeup.",
    "💔 Your ex is coming back. Not even the cemetery could hold them.",
    "🤡 Today you will be humiliated for free. The universe is running a promotion.",
    "🔥 Your libido is alive. Your common sense was found dead.",
    "☠️ Karma did not forget you. It was just waiting for Halloween.",
    "👻 Today a message will haunt you. You wrote it yourself.",
    "🪦 Your relationship is not in crisis. It is in a state of decomposition.",
    "💀 Today you will say “it can’t get worse”. The universe loves that phrase.",
    "🎃 You asked for a sign. You received a tragedy with thematic lighting.",
    "🍺 Your liver asked for help. You sent the location of another bar.",
    "💸 Money does not buy happiness. But apparently you will try.",
    "🤡 Today you will become gossip. Dress appropriately.",
    "🔥 A hot night is predicted. The problem will be explaining the temperature.",
    "👻 Your crush will reply. You will wish they had kept ignoring you.",
    "🪦 Today a hope will be buried. Bring flowers.",
    "💀 Your pride is in terminal condition.",
    "🎃 Halloween is not the only day you wear a mask.",
    "🍺 The hangover will be the only stable relationship in your life.",
    "💸 Your bank believes in ghosts because your money disappears without explanation.",
    "💔 Love is dead. You are still trying to perform mouth-to-mouth resuscitation.",
    "🤡 Your shame will have an audience.",
    "🔥 Today you will do something your sober self will try to deny.",
    "👻 The past knocked on the door. Pretend you are dead.",
    "☠️ Today hell will have a queue. You are already on the priority list.",
    "The Moon saw what you did.",
    "Your guardian angel closed his eyes.",
    "The bill returned from the grave.",
    "So did your ex.",
    "The hangover is already waiting for you.",
    "Karma does not wear a costume.",
    "Your dignity did not arrive alive at Halloween.",
    "The cemetery has more emotional stability than you.",
    "Do not open that message.",
    "You opened it.",
    "Do not reply.",
    "You replied.",
    "Congratulations. Now we have a problem.",
    "The night is young. Your reputation is not.",
    "The devil asked your name. He already knew.",
    "Your card asked for an exorcism.",
    "Alcohol called. Your liver ignored it.",
    "Your ex unblocked you. Hell unlocked a vacancy.",
    "The full moon is not responsible for your decisions.",
    "You are.",
    "The monster under the bed asked you to stop scaring it.",
    "Today bad luck is on duty.",
    "Your future has a terrible surprise.",
    "The surprise already knows where you live.",
    "It is not intuition. It is traumatic experience.",
    "You are not cursed. You are just extremely unlucky.",
    "The universe tried to warn you. You put it on mute.",
    "Destiny called. You let it ring.",
    "Death is inevitable. So is embarrassment.",
    "Happy Halloween. Good luck tomorrow.",
]


# ---------------------------------------------------------------------------
# Embed builders
# ---------------------------------------------------------------------------
def build_panel_embed() -> discord.Embed:
    embed = discord.Embed(
        title="👻 Cursed Horoscope 💀",
        description=(
            "**Click your sign below to receive your cursed prediction.**\n\n"
            "Consult the fortune teller Nazar and find out (or not) what fate has in store for you."
        ),
        color=CURSED_PURPLE,
    )
    embed.set_image(url=GIF_URL)
    embed.set_footer(text="◆ ARCADE · CURSED HOROSCOPE · HALLOWEEN SPECIAL ◆")
    return embed


def build_result_embed(user: discord.abc.User, sign_key: str, phrase: str) -> discord.Embed:
    sign = SIGNS[sign_key]
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")
    embed = discord.Embed(
        title=f"{sign['emoji']}  {sign['name'].upper()} — {sign['title']}",
        description=(
            f"**{user.mention}** consulted the cursed stars.\n\n"
            f"> ### ❝ {phrase} ❞\n\n"
            f"**Horoscope of {today}**"
        ),
        color=CURSED_RED,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_thumbnail(url=GIF_URL)
    embed.set_footer(text="◆ CURSED HOROSCOPE · NO MERCY · NO REFUNDS ◆")
    return embed


# ---------------------------------------------------------------------------
# Persistent panel view (12 sign buttons)
# ---------------------------------------------------------------------------
class CursedHoroscopeView(discord.ui.View):
    """Persistent panel — timeout=None so it survives restarts."""

    def __init__(self, cog: "CursedHoroscope"):
        super().__init__(timeout=None)
        self.cog = cog
        # Build 12 buttons dynamically in 4 rows of 3
        order = [
            "aries", "taurus", "gemini",
            "cancer", "leo", "virgo",
            "libra", "scorpio", "sagittarius",
            "capricorn", "aquarius", "pisces",
        ]
        for i, key in enumerate(order):
            sign = SIGNS[key]
            row = i // 3
            btn = discord.ui.Button(
                label=sign["name"],
                emoji=sign["emoji"],
                style=discord.ButtonStyle.secondary,
                custom_id=f"cursedhoroscope:signo_{key}",
                row=row,
            )
            btn.callback = self._make_callback(key)
            self.add_item(btn)

    def _make_callback(self, sign_key: str):
        async def callback(interaction: discord.Interaction):
            await self._handle_sign(interaction, sign_key)
        return callback

    async def _handle_sign(self, interaction: discord.Interaction, sign_key: str):
        if interaction.channel_id != ALLOWED_CHANNEL_ID:
            await interaction.response.send_message(
                "❌ Cursed Horoscope only works in its dedicated channel.",
                ephemeral=True,
            )
            return

        user = interaction.user
        remaining = self.cog._check_cooldown(user.id)
        if remaining > 0:
            mins = int(remaining // 60)
            secs = int(remaining % 60)
            time_str = f"{mins}m {secs}s" if mins else f"{secs}s"
            await interaction.response.send_message(
                f"⏳ The curse needs rest. Wait **{time_str}**.",
                ephemeral=True,
            )
            return

        self.cog._set_cooldown(user.id)
        await interaction.response.defer()

        # Delete panel → post result → re-post panel (panel always last)
        await self.cog._consult_from_panel(interaction.channel, user, sign_key)


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------
class CursedHoroscope(commands.Cog):
    """Cursed Horoscope mini-game — sticky panel + 12 zodiac buttons."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._cooldowns: dict[int, float] = {}
        self._panel_view: Optional[CursedHoroscopeView] = None
        self._panel_message_id: Optional[int] = None
        self._sticky_lock = False
        self._panel_operation_lock = asyncio.Lock()
        self._load_panel_state()

    def _load_panel_state(self) -> None:
        data = load_json(PANEL_STATE_FILE, {})
        if isinstance(data, dict):
            mid = data.get("message_id")
            self._panel_message_id = int(mid) if mid else None

    def _save_panel_state(self) -> None:
        save_json(PANEL_STATE_FILE, {"message_id": self._panel_message_id})

    def _check_cooldown(self, user_id: int) -> float:
        last = self._cooldowns.get(user_id)
        if not last:
            return 0.0
        elapsed = datetime.now(timezone.utc).timestamp() - last
        remaining = COOLDOWN_SECONDS - elapsed
        return max(0.0, remaining)

    def _set_cooldown(self, user_id: int) -> None:
        self._cooldowns[user_id] = datetime.now(timezone.utc).timestamp()

    async def cog_load(self) -> None:
        self._panel_view = CursedHoroscopeView(self)
        self.bot.add_view(self._panel_view)
        logger.info("CursedHoroscope persistent panel view registered")

    async def _delete_current_panel(self, channel: discord.abc.Messageable) -> None:
        if not self._panel_message_id:
            return
        try:
            old = await channel.fetch_message(self._panel_message_id)
            await old.delete()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass
        self._panel_message_id = None
        self._save_panel_state()

    async def _post_panel(self, channel: discord.abc.Messageable) -> discord.Message:
        view = CursedHoroscopeView(self)
        self._panel_view = view
        self.bot.add_view(view)
        msg = await channel.send(embed=build_panel_embed(), view=view)
        self._panel_message_id = msg.id
        self._save_panel_state()
        return msg

    async def _consult_from_panel(
        self,
        channel: discord.abc.Messageable,
        user: discord.abc.User,
        sign_key: str,
    ) -> discord.Message:
        """Post the cursed prediction and restore the sticky panel underneath it."""
        async with self._panel_operation_lock:
            await self._delete_current_panel(channel)

            sign = SIGNS[sign_key]
            phrase = random.choice(sign["phrases"])
            embed = build_result_embed(user, sign_key, phrase)
            result_msg = await channel.send(embed=embed)

            await self._post_panel(channel)
            return result_msg

    # ------------------------------------------------------------------
    # Sticky behaviour — keep panel at the bottom of the channel
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.channel.id != ALLOWED_CHANNEL_ID:
            return
        if message.author.bot:
            return
        if not self._panel_message_id:
            return
        if self._sticky_lock:
            return

        self._sticky_lock = True
        try:
            async with self._panel_operation_lock:
                channel = message.channel
                await self._delete_current_panel(channel)
                await self._post_panel(channel)
        except Exception:
            logger.exception("CursedHoroscope sticky repost failed")
        finally:
            self._sticky_lock = False

    # ------------------------------------------------------------------
    # Admin: post the fixed panel
    # ------------------------------------------------------------------
    @app_commands.command(
        name="cursedhoroscope_panel",
        description="[ADMIN] Post the permanent Cursed Horoscope arcade panel",
    )
    @app_commands.guild_only()
    async def cursedhoroscope_panel(self, interaction: discord.Interaction):
        if ALLOWED_CHANNEL_ID and interaction.channel_id != ALLOWED_CHANNEL_ID:
            await interaction.response.send_message(
                "❌ This panel can only be posted in the dedicated Cursed Horoscope channel.",
                ephemeral=True,
            )
            return

        if self._panel_message_id:
            try:
                old = await interaction.channel.fetch_message(self._panel_message_id)
                await old.delete()
            except Exception:
                pass

        view = CursedHoroscopeView(self)
        self._panel_view = view
        self.bot.add_view(view)

        embed = build_panel_embed()
        await interaction.response.send_message(embed=embed, view=view)
        msg = await interaction.original_response()
        self._panel_message_id = msg.id
        self._save_panel_state()
        logger.info(
            "CursedHoroscope panel posted by %s in channel %s (msg %s)",
            interaction.user,
            interaction.channel_id,
            msg.id,
        )

    # ------------------------------------------------------------------
    # Admin: test mode — works in any channel
    # ------------------------------------------------------------------
    @app_commands.command(
        name="cursedhoroscope_test",
        description="[ADMIN] Test Cursed Horoscope — works in any channel",
    )
    @app_commands.guild_only()
    async def cursedhoroscope_test(self, interaction: discord.Interaction):
        await interaction.response.defer()
        human = interaction.user
        # Pick a random sign for the test
        sign_key = random.choice(list(SIGNS.keys()))
        sign = SIGNS[sign_key]
        phrase = random.choice(sign["phrases"])
        embed = build_result_embed(human, sign_key, phrase)
        await interaction.followup.send(
            content=f"🧪 **Test mode** — {human.mention} received a cursed prediction:",
            embed=embed,
        )

    @cursedhoroscope_panel.error
    @cursedhoroscope_test.error
    async def admin_cmd_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(
                "❌ You do not have one of the authorized roles for this command.",
                ephemeral=True,
            )
        else:
            logger.exception("CursedHoroscope command error: %s", error)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ Something went wrong.",
                    ephemeral=True,
                )


async def setup(bot: commands.Bot):
    await bot.add_cog(CursedHoroscope(bot))
