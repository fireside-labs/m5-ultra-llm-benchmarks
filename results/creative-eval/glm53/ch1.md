# Patch Notes for a Broken World

## Chapter 1: Build 0.9.7

I died on a Tuesday, which felt about right. Nothing in my life had ever happened on an important day.

I should probably explain what I was doing when it happened, because it's the only reason I know what I know now, and I've had a lot of time to think about how unfair that is.

My name was Yui Tanaka. I was twenty-nine, and for six years I was a quality assurance tester at Hoshino Interactive, which is a fancy way of saying I got paid barely anything to break a beautiful thing on purpose. The game was called *Aetherfall Online*. You might have played it. You probably did play it — ten million accounts at its peak, the floating continents, the sky-whales over the Verdant Shelf, the final raid that nobody ever cleared because the servers shut down before anyone could.

They shut the servers down three years ago. Licensing dispute. The whole world — every village, every questline, every NPC with their carefully written two hundred lines of dialogue — switched off on a Friday afternoon while I sat in the office and watched the player count tick down to zero. I stayed until the last number vanished. I don't know what I expected to feel. Emptiness, maybe. What I actually felt was that I'd watched a city's lights go out one by one and then been asked to hand in my badge on the way out.

So when a file showed up on a retro-gaming forum last month — a leaked server build, complete, runnable — I cleared my weekend. I canceled exactly one plan, which was dinner with my mother, who told me I was going to die alone in front of a computer, and I said something glib back, and that was the last thing I ever said to her. Remember that, later, when you wonder why I'm trying so hard.

Here's the thing about leaked builds. They're not the polished game. They're the *skeleton* of the game — debug tools left in, placeholder textures, test items, entire zones the players never saw because we cut them. I knew that build better than anyone alive, because I was one of the maybe forty people on Earth who had ever run it. I knew where the bodies were buried. Sometimes literally; there was an unmarked quest corpse under the well in Milbrook and I could tell you the designer's name who put it there and why she was laughing about it.

So on Tuesday night I was in the pre-launch version of the world. Build 0.9.7. The sky in that build flickered at the horizon seam — a rendering bug I filed eleven times, ticket #4471, *horizon seam flicker, low priority, won't fix*. I was standing in the starting meadow looking at that flicker out of pure nostalgia when I noticed my chest felt strange. Not painful. Just strange, like a door in a house you've lived in your whole life has suddenly swung open onto a room that shouldn't exist.

I remember thinking, very clearly: *that's not good.*

I remember reaching for the mouse, because some idiotic part of my brain wanted to file a ticket.

Then the meadow folded up like a closing umbrella, and there was no more Tuesday.

---

I woke up on grass, and the first thing I did — before opening my eyes, before breathing, before any of the sensible things — was check whether the horizon was flickering.

It was. A faint stutter at the seam where the sky met the sea, like a screen tearing. Ticket #4471. *Low priority. Won't fix.*

I sat up. The meadow stretched away from me in every direction, silver-gold in early light, dotted with those absurd one-hit-kill rabbits that the design team had balanced at three in the morning and never revisited. The Windmere starting zone. I'd run through this grass — this exact grass, the same texture, the same three-bushes-then-a-rock pattern repeating — thousands of times. I knew that if I walked ninety paces east I'd find the pond with the fishing tutorial NPC, and that his name was Garam, and that he had a hidden line of dialogue you could only trigger by standing in the pond for four minutes, and that the line was "*Fish fear me. Respect that.*"

I counted the paces. Ninety. Pond. Garam.

"Fish fear me," he said, four minutes later, unprompted, when I'd stood there like an idiot. "Respect that."

I laughed until my eyes stung, and then I sat down on the bank and made myself think, because panic is just a bug you haven't reproduced yet.

Hypothesis one: I was dreaming. I pinched myself. Inconclusive; pinching yourself is always inconclusive.

Hypothesis two: this was the leaked build, and I'd never woken up from my desk at all. I looked up at the horizon seam. The flicker was wrong for a rendering bug — it had *depth* to it now, like the sky was a curtain and something behind it was breathing. Bugs don't breathe.

Hypothesis three arrived uninvited, and it had teeth, so I stood up and did what I always do when a hypothesis has teeth: I tested the UI.

"Menu," I said.

It opened. Not with the old chime — with a sound I'd never heard, a low glassy tone like a struck fingernail, and I want you to understand that *Aetherfall* didn't have a voice-activated menu. Nobody's build had a voice-activated menu.

**STATUS**

**Name:** Yui Tanaka
**Class:** QA Tester
**Level:** 1
**HP:** 12/12
**Build:** 0.9.7 — Pre-Launch
**Connected Players:** 1 / 10,000,000

**World Launch in: 29 days, 14 hours, 06 minutes**

I read it four times. The bottom two lines didn't change. The countdown didn't change. The player count — *one* — didn't change.

"Class: QA Tester," I said out loud, to nobody. "That's not a class. That was never a class. That's a placeholder we put in the character creation screen so the dropdown wouldn't be empty."

The dropdown, in the final game, had contained Warrior, Mage, Ranger, Cleric, and — after a fight in a design meeting I attended — Bard. The QA placeholder had been visible for exactly one internal build before someone noticed and deleted it. I know, because I was the one who found the exploit where you could still select it by keyboard-navigating the screen in a specific broken order, and for one glorious afternoon the entire QA department had run around the test servers as invisible level-0 entities that walked through walls.

I had assumed they deleted the class. It occurred to me now, standing in a meadow that should not exist, under a sky that should not flicker, that you don't have to delete a thing to remove it from a menu. You just have to hide it.

"Skills," I said.

**SKILLS**

**Inspect** — Reveal underlying data. Always active.
**Noclip** — Pass through geometry. Uses remaining today: 1
**Command Line** — Speak to the world in its own language. Uses remaining today: 1
**Regression** — Restore an object to a previous state. Uses remaining: 3 total. *No refresh.*
**Bug Report** — Unknown. *Requires escalation.*

I want to be honest with you about what I felt reading that list, because it wasn't joy. It was the specific cold feeling of finding your own name on a document you weren't supposed to see. *Regression — no refresh.* I knew what that meant. I'd written tooltips like that. It meant the resource was finite and someone had decided, deliberately, how finite.

There was a butterfly on a foxglove near the bank. I looked at it.

**inspect:**
**Entity: Faewing Flutterby (ambient)**
**Type: Decoration**
**Flags: [no_collision] [no_death] [despawn_ignored]**
**Notes:** Placeholder fauna. Do not ship.

*Do not ship.* Every model and script in that build carried the same little graveyard of comments. *Do not ship. Placeholder. Ask Keiko. Won't fix.* I had read thousands of them. I had written hundreds. It had never once occurred to me, in six years of reading the skeleton of that world, to ask what would happen if the skeleton ever woke up.

So let me tell you the theory I built on that riverbank, standing in a world one month before its own launch. It's the only theory that fits, and I've had time to refine it, and I still hate it.

*Aetherfall* was never invented. It was *translated*. The art book said as much, in the one line of corporate mysticism everyone laughed at: "We did not build this world; we listened for it." Hoshino's founders ran some kind of scanning process — nobody below the director level ever learned how — and what we testers got our hands on, what ten million players fell in love with, was a *copy*. A copy with debug flags and placeholder butterflies and a horizon seam that wouldn't fix. And when the servers shut down, the copy switched off.

But a translation, once made, exists independently of the original. And a copy, once made, keeps running as long as something runs it.

This world was real before we ever listened to it. Then we copied it, mined it for content, patched it, broke it, fixed it, shipped it, played it, and shut it down. And now the copy had come back online — build 0.9.7, the skeleton build, the one with the seams showing — and in twenty-nine days, ten million players were going to log in and pour into this meadow like tourists into a city whose residents haven't been told.

Connected players: one. Me. The QA placeholder class. The hidden option, kept in, the way you keep a spare key.

I sat back down on the bank, because my legs had opinions, and Garam the fishing NPC watched me with his flat painted eyes, and I thought: *NPCs.* That was the next thing to test. Because there was one thing in the design docs marked with more red tape than anything else, one thing the director locked down so hard that even the lead writers only saw fragments, and it wasn't the final boss.

It was the question of whether the people inside the world knew what they were.

The official line was: they don't, they can't, the question is out of scope. But I once found a test script — one line, buried in a deprecated file — that read: `IF npc_awareness_flag == TRUE, escalate_to_director`. Somebody had written a check for it. You don't write a check for something you're certain can't happen.

So I walked back to Windmere village, and I went to the general store, and I bought a rope and a torch and an apple from the shopkeeper, who is named Merta in the dialogue file and who has, in the shipped game, exactly seven lines, none of which involve noticing anything unusual about a customer.

She counted out my change, and then she looked up at me, and her eyes were doing something her eyes were never animated to do. They were afraid.

"You're one of the Builders," she said. Not a question.

I said the first thing that came into my head, which was: "What makes you say that?"

"Because you looked at the rope before you bought it." Her hands had gone still on the counter. "The Others never look at things. They look *through* them, at numbers only they can see. But you looked at the rope the way my mother looked at rope. And then you looked at me—" she stopped, and her jaw set, and it was the bravest thing I have ever seen, in any world, "—and I felt it. Like a hand going through my pockets. So. Are they coming back? The Others? Because the sky's been counting down, and the Elder says we shouldn't speak of it, and everyone pretends, but *everyone knows*, and—"

"Merta." I said her name and she flinched, and I understood suddenly, horribly, that to her I was not a lost girl in a meadow. I was a piece of the machinery that had owned her life, come back with its hand in her pockets. I lowered my voice. "Look at me. **Inspect**."

I didn't even mean to say it out loud. The skill fired anyway, and the world peeled back like wet paper, and there she was:

**inspect:**
**Entity: Merta of Windmere**
**Type: NPC (vendor, tier 2)**
**Flags: [awareness: 0.03] [flagged_for_wipe: DAY_30]**

**flagged_for_wipe. Day 30.**

Launch day.

I looked past her, through the shop window, at the village square — at the children I'd watched respawn on a loop for six years, at the Elder by the well who gave out the fetch quest, at all of it, beautiful and doomed — and the Inspect skill, always active, whether I wanted it or not, obligingly showed me what it showed for every single one of them.

Every window in the village had the same two words hanging over it like frost:

**flagged_for_wipe. Day 30.**

The countdown said twenty-nine days, fourteen hours, and six minutes.

I had a Command Line with one use left today, three Regressions total, and six years of knowing exactly how this world was built, and exactly where its designers had hidden every switch, every cut quest, every unmarked grave and deprecated god.

I turned back to Merta, who was watching me the way you watch a verdict.

"First," I said, "I need to know everything the Elder won't tell you. And then—" I pulled up the skill list again, and looked at the last line, the one marked *requires escalation*, and felt something in my chest that was not fear, or if it was fear, it was the useful kind. "Then I need to file a bug report."

Because here's what I knew that nobody else alive knew — not the players, not the NPCs, not whoever or whatever was running this skeleton of a world with its seams showing:

*Build 0.9.7 was never cleared for launch.*

There's a reason the shipped game's final zone was never finished. There's a reason the raid was never cleared. There's a version of the world that was supposed to go live on Day 30 — and it is not this one, and the thing the patch notes would have called *The Wipe* is not a patch at all.

It's a rollback. And I was the only person in two worlds who had ever read the changelog.