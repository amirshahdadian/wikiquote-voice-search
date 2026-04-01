# User Flow — Simple Web App for “Which Quote?”

## 1. Product overview

The final product is a simple web app that allows users to interact with a Wikiquote-based quote autocomplete system through voice. The app recognizes who is speaking, transcribes the spoken request, searches the quote database, and replies with a natural-language spoken answer using the voice style associated with the recognized user.

The web app combines four main capabilities:

1. **Quote autocomplete and retrieval** from a Wikiquote graph database
2. **Voice input transcription** through Automatic Speech Recognition (ASR)
3. **Speaker recognition** to identify the current user
4. **Personalized spoken responses** through Text-to-Speech (TTS)

---

## 2. Main goals of the user flow

The user flow is designed to let a user:

- access the web app from a browser
- register as a new speaker
- save a preferred response voice
- ask for quote completions or quote information by speaking
- be recognized automatically in future sessions
- receive both text and audio responses
- continue the interaction in a conversational way

---

## 3. Actors

### Primary actor
- **Registered user**: a person who has already created a profile and provided voice samples

### Secondary actor
- **New user**: a person using the system for the first time, who must register before using speaker recognition features

### System
- **Web app interface**
- **ASR module**
- **Speaker Identification module**
- **Wikiquote graph search engine**
- **Chatbot / response generation module**
- **TTS module**

---

## 4. Assumptions for the web app

The app is assumed to have:

- a landing page
- a registration page
- a main interaction page
- a user settings/profile page
- microphone access in the browser
- a backend connected to:
  - a graph database built from Wikiquote
  - a full-text quote index
  - speaker embeddings database
  - ASR service
  - TTS service

---

## 5. High-level user journey

At a high level, the user journey looks like this:

1. User opens the web app
2. User chooses to register or start speaking
3. If new, the user records voice samples and selects preferences
4. If returning, the user directly gives a voice command
5. The system transcribes the request
6. The system identifies the speaker
7. The system searches the Wikiquote graph
8. The system generates a spoken and written answer
9. The user continues with follow-up questions or starts a new query

---

## 6. Main pages and screens

### 6.1 Landing page
Purpose:
- Introduce the app
- Let users begin interaction

Main UI elements:
- App title and short description
- “Start speaking” button
- “Register new user” button
- “Login / Continue” section
- Microphone permission prompt if needed

---

### 6.2 Registration page
Purpose:
- Create a user profile for speaker recognition and personalized TTS

Main UI elements:
- Name / nickname field
- Optional email or group identifier
- Voice preference selector
- “Record voice samples” section
- Progress indicator for sample collection
- “Save profile” button

---

### 6.3 Main interaction page
Purpose:
- Let users ask questions vocally and receive results

Main UI elements:
- Microphone button
- Text input fallback
- Transcript display area
- Response area
- Quote source panel
- Audio playback controls
- Conversation history panel

---

### 6.4 Profile / settings page
Purpose:
- Manage saved preferences

Main UI elements:
- User profile info
- Preferred TTS voice/style
- Re-record voice samples
- Delete account / reset profile
- Test response voice button

---

## 7. Detailed end-to-end user flow

## 7.1 Entry flow

### Step 1 — Open app
The user opens the web app in a browser.

### Step 2 — View landing page
The user sees:
- a short explanation of the app
- a button to start interaction
- a button to register as a new user

### Step 3 — Grant microphone access
If microphone access has not already been granted, the browser prompts the user for permission.

#### Possible outcomes:
- **Permission granted** → continue
- **Permission denied** → show a warning and offer text input fallback

---

## 7.2 New user registration flow

### Step 1 — Choose “Register new user”
The user clicks the registration button.

### Step 2 — Enter identity information
The user fills in:
- display name or nickname
- optional preferences for the TTS voice

### Step 3 — Record enrollment samples
The system asks the user to record multiple short voice samples.

For example:
- “Please read sentence 1”
- “Please read sentence 2”
- “Please read sentence 3”

These recordings are used to create the speaker embedding.

### Step 4 — Generate speaker embedding
The Speaker Identification module extracts a voice embedding from the recorded samples.

### Step 5 — Save profile
The system stores:
- user ID
- display name
- speaker embedding
- TTS preferences

### Step 6 — Registration success
The system confirms that the user has been registered successfully.

### Step 7 — Redirect to main interaction page
The user is taken to the main voice interaction interface.

---

## 7.3 Returning user flow

### Step 1 — Start from landing page
The user clicks “Start speaking”.

### Step 2 — Record voice command
The user clicks the microphone button and says a request.

Example requests:
- “Complete this quote: To be or not to...”
- “Who said knowledge is power?”
- “Find a quote about freedom.”

### Step 3 — Audio capture
The web app sends the recorded audio to the backend.

### Step 4 — Speech transcription
The ASR module converts the spoken request into text.

### Step 5 — Speaker recognition
The Speaker Identification module compares the current voice input with stored voice embeddings.

#### Possible outcomes:
- **User recognized with sufficient confidence**
- **User not recognized**
- **Recognition uncertain**

### Step 6 — Load user preferences
If the speaker is recognized, the system loads that user’s saved TTS configuration.

### Step 7 — Interpret user intent
The chatbot module determines what the user wants.

Possible intents include:
- quote completion
- author/source identification
- quote search by topic
- follow-up question
- clarification request

### Step 8 — Query the Wikiquote graph
The system searches the graph database and full-text index for the best matching quote or set of quotes.

### Step 9 — Rank and select results
The system chooses the most relevant quote match and collects:
- full quote text
- speaker/author
- source page or citation node
- optional related quotes

### Step 10 — Generate natural language response
The chatbot creates a response in natural language.

Example:
> “The best matching quote is ‘To be, or not to be: that is the question,’ by William Shakespeare, from *Hamlet*.”

### Step 11 — Synthesize response audio
The TTS module generates a spoken response using the user’s associated voice settings.

### Step 12 — Display and play result
The web app shows:
- recognized user name
- transcript of the request
- answer text
- matched quote
- source information

At the same time, the response audio is played automatically or made available through a play button.

### Step 13 — Continue the session
The user can:
- ask another question
- refine the previous request
- click on related quotes
- replay the answer audio

---

## 8. Main conversation flow

After the first successful interaction, the app enters a repeated conversation loop.

### Repeated loop:
1. User speaks
2. System records audio
3. ASR transcribes the request
4. Speaker recognition confirms the speaker
5. Chatbot interprets the request
6. Wikiquote graph is searched
7. Best result is selected
8. Response text is generated
9. TTS produces spoken output
10. User hears and sees the response
11. User asks another question or ends the session

---

## 9. Core interaction scenarios

## 9.1 Scenario A — Quote autocomplete

### User goal
Complete a partially remembered quote.

### Example
User says:
> “Complete this quote: I think, therefore...”

### System behavior
- transcribes the request
- detects quote completion intent
- searches the full-text citation index
- returns the best matching result

### Output
- completed quote
- author/source
- spoken response

---

## 9.2 Scenario B — Source identification

### User goal
Find out who said a quote.

### Example
User says:
> “Who said knowledge is power?”

### System behavior
- identifies quote lookup intent
- finds exact or approximate match
- returns speaker attribution and source page

### Output
- quote attribution
- optional additional context
- spoken explanation

---

## 9.3 Scenario C — Search by theme

### User goal
Find a quote related to a topic.

### Example
User says:
> “Find a quote about hope.”

### System behavior
- identifies thematic search intent
- searches quotes semantically or by keywords
- returns one or more relevant results

### Output
- best quote
- author
- optional alternatives

---

## 9.4 Scenario D — Follow-up conversation

### User goal
Ask follow-up questions naturally.

### Example
User says:
> “Who wrote that?”
> “Give me another one.”
> “Read it again.”

### System behavior
- uses session context
- links the new request to the previous response
- answers without requiring the quote to be repeated

### Output
- contextual response
- updated audio reply

---

## 10. Alternative and exception flows

## 10.1 Speaker not recognized

### Situation
The user speaks, but the system cannot confidently match the voice to a stored embedding.

### System response
The app shows and says:
> “I could not recognize the speaker. Please try again or register as a new user.”

### Next actions
The user can:
- retry speaking
- choose their profile manually
- register as a new user

---

## 10.2 Low ASR confidence

### Situation
The audio is noisy or unclear, and the transcription is unreliable.

### System response
The app shows:
> “I’m not sure I understood. Please repeat your request.”

### Next actions
The user can:
- record again
- use text input instead

---

## 10.3 No quote found

### Situation
The system cannot find a strong match in the Wikiquote graph.

### System response
The app shows and says:
> “I could not find an exact match. Here are the closest results.”

### Next actions
The user can:
- pick one of the proposed results
- rephrase the request
- search by author or topic

---

## 10.4 Multiple close matches

### Situation
The query matches several similar quotes.

### System response
The app asks for clarification:
> “I found multiple possible matches. Did you mean the quote by Shakespeare or the one by Churchill?”

### Next actions
The user chooses one option verbally or by clicking on screen.

---

## 10.5 Microphone permission denied

### Situation
The browser blocks microphone access.

### System response
The app displays:
> “Microphone access is required for voice interaction. You can enable it in your browser settings or use text input.”

### Next actions
The user can:
- enable microphone access
- continue with typed input

---

## 10.6 User wants to change TTS voice

### Situation
A recognized user wants a different response voice style.

### System response
The user goes to profile settings and updates:
- preferred voice
- speed
- style or model option

### Outcome
Future responses use the updated voice settings.

---

## 11. Screen-level user flow

## 11.1 Landing page flow
- User opens app
- User reads app description
- User clicks:
  - “Register new user”, or
  - “Start speaking”

---

## 11.2 Registration flow
- User enters name
- User chooses TTS preferences
- User records required voice samples
- System validates audio quality
- System generates embedding
- System saves profile
- User is redirected to main page

---

## 11.3 Main interaction flow
- User clicks microphone
- User speaks request
- Audio is uploaded
- ASR creates transcript
- Speaker ID identifies user
- Chatbot determines intent
- Search engine retrieves quote(s)
- Response is generated
- TTS audio is created
- Web app displays result and plays answer

---

## 11.4 Follow-up flow
- User asks another question
- System uses session context
- System produces follow-up response
- Session history is updated

---

## 12. Functional output shown to the user

For each successful interaction, the interface should show:

- **Recognized speaker**
- **Transcript of the spoken query**
- **Best matching quote**
- **Author / source**
- **Natural-language explanation**
- **Audio playback**
- **Optional related quotes**

Example result card:

- Recognized user: Maria
- You said: “Complete this quote: To be or not to...”
- Best match: “To be, or not to be: that is the question.”
- Author: William Shakespeare
- Source: *Hamlet*
- Audio response: available

---

## 13. Suggested UX behavior

To keep the app simple and usable, the web app should:

- clearly show when it is listening
- clearly show when it is processing
- display the transcript before the answer
- let the user replay the spoken response
- keep a short visible conversation history
- allow text input as a fallback
- provide clear recovery steps for errors

---

## 14. End-of-session flow

The user may end the session by:
- closing the browser tab
- clicking “End session”
- staying inactive until timeout

At the end of the session:
- the conversation history may be cleared or saved
- the speaker profile remains stored
- TTS preferences remain associated with the user

---

## 15. Final concise narrative

The user opens the web app and either registers or immediately starts speaking. A new user records voice samples so the system can create a speaker embedding and save a profile with preferred TTS settings. A returning user simply presses the microphone button and asks a question. The system transcribes the audio, identifies the speaker, searches the Wikiquote graph for the best matching citation, and generates a natural-language response. The answer is shown on screen and also spoken back using the voice preferences associated with the recognized user. The user can then continue the interaction conversationally, ask follow-up questions, or end the session.