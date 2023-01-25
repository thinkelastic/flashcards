import json
import requests
import os
import openai
import genanki
import random
import string
import html
import collections
import genxword.control

openai.api_key = os.getenv("OPENAI_API_KEY")

PACKAGE_SIZE = 50
OXFORD_APP_ID = os.getenv("OXFORD_APP_ID")
OXFORD_APP_KEY = os.getenv("OXFORD_APP_KEY")

DEFAULT_LOCALE = 'en-us'
GENERIC_LOCALE = 'en'
OXFORD_WORD_URL = string.Template(
    "https://od-api.oxforddictionaries.com/api/v2/entries/${locale}/${word}")

OXFORD_LEMMA_URL = string.Template(
    "https://od-api.oxforddictionaries.com/api/v2/lemmas/${locale}/${word}")

ENABLE_CACHE = True
STORY_PROMPT = string.Template('''Write 3 sentences using the word ${word}''')
CLUE_PROMPT = string.Template('''Generate a crossword clue for "${word}"''')

WORDS_PATH = 'WordFrequencyPython/json/words.json'
CACHE_DIRECTORY = os.path.join('cache', DEFAULT_LOCALE)
AUDIO_DIRECTORY = os.path.join(CACHE_DIRECTORY, 'media')
DICTIONARY_DIRECTORY = os.path.join(CACHE_DIRECTORY, 'dictionary')
STORY_DIRECTORY = os.path.join(CACHE_DIRECTORY, 'story')
CLUE_DIRECTORY = os.path.join(CACHE_DIRECTORY, 'clue')
FLASHCARD_DIRECTORY = os.path.join('output', DEFAULT_LOCALE)

FRONTSIDE_CLOZECARD = '''<font size="5px">{{Synonym}}</font>
<hr>
<font size="4px">{{cloze:Story}}</font>'''

BACKSIDE_CLOZECARD = '''<font size="5px">{{Synonym}}</font>
<hr>
<font size="4px">{{cloze:Story}}</font>
<hr>
<font size="8px">{{Word}}</font>{{Audio}}
<br>
<font size="3px">{{Phonetic}}</font>
<hr>
<font size="5px">{{Meaning}}</font>'''

# Declaring Card namedtuple()
Card = collections.namedtuple('Card', [
    'word',
    'phoneticSpelling',
    'meanings',
    'synonyms',
    'pronounced_word',
    'story'])

def download_pronounciation(word, url, path):
    output_file = os.path.join(path, "%s.mp3" % word)
    
    if not os.path.exists(path):
        # Create a new directory because it does not exist
        os.makedirs(path)
        
    if not os.path.exists(output_file):
        response = requests.get(url, allow_redirects=True)
        
        if response.status_code != 200:
            response.raise_for_status()
        
        # The response's audio_content is binary.
        with open(output_file, "wb") as out:
            # Write the response to the output file.
            out.write(response.content)
        
    return output_file

def lookup_lemma(word):
    response = requests.get(
        OXFORD_LEMMA_URL.safe_substitute({'locale': GENERIC_LOCALE, 'word': word}),
        headers={'app_id': OXFORD_APP_ID, 'app_key': OXFORD_APP_KEY}
    )
            
    if response.status_code == 200:
        lemma = response.json()['results'][0]['lexicalEntries'][0]['inflectionOf'][0]['text']
        
        # Try to get the word from the default locale
        response = requests.get(
            OXFORD_WORD_URL.safe_substitute({'locale': DEFAULT_LOCALE, 'word': lemma}),
            headers={'app_id': OXFORD_APP_ID, 'app_key': OXFORD_APP_KEY}
        )
    
        if response.status_code != 200:
            # Try to get the word from the generic locale
            response = requests.get(
                OXFORD_WORD_URL.safe_substitute({'locale': GENERIC_LOCALE, 'word': word}),
                headers={'app_id': OXFORD_APP_ID, 'app_key': OXFORD_APP_KEY}
            )

    if response.status_code != 200:
        response.raise_for_status()
    else:
        return response

def lookup_word(word):
    word_cache = os.path.join(DICTIONARY_DIRECTORY, "%s.json" % word)
    dictionary_entry = None
    
    if os.path.exists(word_cache):
        with open(word_cache) as file:
            dictionary_entry = json.load(file)
    else:
        # Try to get the word from the default locale
        response = requests.get(
            OXFORD_WORD_URL.safe_substitute({'locale': DEFAULT_LOCALE, 'word': word}),
            headers={'app_id': OXFORD_APP_ID, 'app_key': OXFORD_APP_KEY}
        )
         
        if response.status_code != 200:
            response = lookup_lemma(word)
            
        if response.status_code != 200:
            response.raise_for_status()
            
        # The response's audio_content is binary.
        with open(word_cache, "w") as out:
            # Write the response to the output file.
            json.dump(response.json(), out)
            
        dictionary_entry = response.json()
        
    return dictionary_entry

def generate_clue(word, salt = 0):
    clue_cache_dir = os.path.join(CLUE_DIRECTORY, str(salt))
    clue_cache = os.path.join(clue_cache_dir, "%s.json" % word)
    
    if not os.path.exists(clue_cache_dir):
        os.makedirs(clue_cache_dir)

    clue = None

    if ENABLE_CACHE and os.path.exists(clue_cache):
        with open(clue_cache) as file:
            clue = json.load(file)
    else:
        print("Calling OAI to generate clue for %s" % word)
        clue = openai.Completion.create(
            model="text-davinci-003",
            prompt=CLUE_PROMPT.safe_substitute({'word': word}),
            temperature=0.6,
            max_tokens=256,
            top_p=1,
            frequency_penalty=1,
            presence_penalty=1
        )
        
        with open(clue_cache, 'w') as file:
            json.dump(clue, file)
    
    return clue

def generate_story(word, meanings, salt = 0):
    story_cache_dir = os.path.join(STORY_DIRECTORY, str(salt))
    story_cache = os.path.join(story_cache_dir, "%s.json" % word)
    
    if not os.path.exists(story_cache_dir):
        os.makedirs(story_cache_dir)

    story = None

    if ENABLE_CACHE and os.path.exists(story_cache):
        with open(story_cache) as file:
            story = json.load(file)
    else:
        print("Calling OAI to generate story for %s" % word)
        story = openai.Completion.create(
            model="text-davinci-003",
            prompt=STORY_PROMPT.safe_substitute({'word': word, 'definition': meanings}),
            temperature=0.6,
            max_tokens=256,
            top_p=1,
            frequency_penalty=1,
            presence_penalty=1
        )
        
        with open(story_cache, 'w') as file:
            json.dump(story, file)
    
    return story

                                       
def create_card_details(word, meanings, salt = 0):
    dictionary_entry = lookup_word(word)
    story = generate_story(word, meanings, salt)
    
    first_entry = dictionary_entry['results'][0]['lexicalEntries'][0]['entries'][0]
    
    phoneticSpelling = None
    audioFile = None
    
    if 'pronunciations' in first_entry:
        for pronounciation in first_entry['pronunciations']:
            if 'phoneticSpelling' in pronounciation:
                phoneticSpelling = pronounciation['phoneticSpelling']
            if 'audioFile' in pronounciation:
                audioFile = pronounciation['audioFile']
            if phoneticSpelling and audioFile:
                break
    
    pronounced_word = None
    if audioFile:
        pronounced_word = download_pronounciation(word, audioFile, AUDIO_DIRECTORY)
   
    synonyms = ''
    if 'synonyms' in first_entry['senses'][0]:
        synonyms = [key['text'] for key in first_entry['senses'][0]['synonyms']]
    
    return Card(
        word,
        phoneticSpelling, 
        meanings,
        synonyms,
        pronounced_word,
        story['choices'][0]['text'])

def generate_clozecards(words, deck, package, salt):
    word_model = genanki.Model(
        random.randrange(1 << 30, 1 << 31),
        'Vocabulary Model',
        fields=[
            {'name': 'Word'},
            {'name': 'Phonetic'},
            {'name': 'Audio'},
            {'name': 'Meaning'},
            {'name': 'Synonym'},
            {'name': 'Story'}
        ],
        templates=[
            {
            'name': 'Card 1',
            'qfmt': FRONTSIDE_CLOZECARD,
            'afmt': BACKSIDE_CLOZECARD,
            },
        ])
    
    for key, value in words:
        print("Processing '%s'" % key)
        card = create_card_details(key, value['meanings'], salt)
        
        cleanedup_story = '<br>'.join(
            [line.rstrip() for line in card.story.splitlines() if line.strip()])
        
        word_choices = [card.word] + random.sample(card.synonyms, min(len(card.synonyms), 4))

        random.shuffle(word_choices)
        
        for i in range(0, len(card.meanings)):
            card.meanings[i] = html.escape(card.meanings[i])
            
        note = genanki.Note(
            model=word_model,
            fields=[
                html.escape(card.word),
                card.phoneticSpelling or "",
                '[sound:%s.mp3]' % card.word, 
                '<br><br>'.join(card.meanings),
                ', '.join(word_choices),
                cleanedup_story.replace(card.word, "{{c1::%s}}" % card.word),
            ])
            
        deck.add_note(note)
        
        if card.pronounced_word and os.path.exists(card.pronounced_word):
            package.media_files.append(card.pronounced_word)

def generate_crossword(words, output_path, salt=0):
    gen = genxword.control.Genxword(auto=True, mixmode=False)
    
    random.shuffle(words)
    
    wordlist = []
    for key, value in words:
        print("Processing '%s'" % key)
        clue = generate_clue(key, salt)
        word = key + " " + clue['choices'][0]['text'].strip().replace('"', '')
        wordlist.append(word)
        
    gen.wlist(wordlist)
    gen.grid_size()
    gen.gengrid(output_path + " (" + str(salt) + ")", saveformat="p")
        
def main():
    words = []
    with  open(WORDS_PATH, 'r') as words_file:    
        words.extend(json.load(words_file).items())
    
    print ("Found %d words" % len(words))
    
    for packageIndex in range(0, len(words), PACKAGE_SIZE):
        if (packageIndex > PACKAGE_SIZE * 3):
            break
        
        anki_package = "Vocabulary_%d-%d.apkg" % (packageIndex, packageIndex + PACKAGE_SIZE - 1)
        crossword = 'Crossword %d-%d' % (packageIndex, packageIndex + PACKAGE_SIZE - 1)
        flashcard_path = os.path.join(FLASHCARD_DIRECTORY, anki_package)
        crossword_path = os.path.join(FLASHCARD_DIRECTORY, crossword)
        
        print("Generating package %d-%d" % (packageIndex, packageIndex + PACKAGE_SIZE -1))

        
        selection = words[packageIndex:packageIndex + PACKAGE_SIZE - 1]
            
        if not os.path.exists(flashcard_path):
            deck = genanki.Deck(random.randrange(1 << 30, 1 << 31), anki_package)
            package = genanki.Package(deck)
            
            generate_clozecards(selection, deck, package, 1)
            package.write_to_file(flashcard_path)
        
        if not os.path.exists(crossword_path):
            generate_crossword(selection, crossword_path, 0)
            generate_crossword(selection, crossword_path, 1)
            
       

if __name__ == '__main__':
    main()