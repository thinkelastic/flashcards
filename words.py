import json
import requests
import os
import openai
import genanki
import random
import string
import collections

openai.api_key = os.getenv("OPENAI_API_KEY")

OXFORD_APP_ID = os.getenv("OXFORD_APP_ID")
OXFORD_APP_KEY = os.getenv("OXFORD_APP_KEY")

LOCALE = 'en-us'
OXFORD_URL = string.Template(
    "https://od-api.oxforddictionaries.com/api/v2/entries/${locale}/${word}")

ENABLE_STORY_CACHE = False
STORY_PROMPT = string.Template('''Write 3 sentences using the word ${word}''')

WORDS_PATH = 'WordFrequencyPython/json/words.json'
AUDIO_DIRECTORY = os.path.join('media', LOCALE)
CACHE_DIRECTORY = os.path.join('cache', LOCALE)

FRONTSIDE_FLASHCARD = '''<font size="8px">{{Word}}</font>{{Audio}}
<br>
<font size="3px">{{Phonetic}}</font>
<hr>
<font size="5px">{{Meaning}}</font>'''

BACKSIDE_FLASHCARD = '''<font size="8px">{{Word}}</font>{{Audio}}
<br>
<font size="3px">{{Phonetic}}</font>
<hr>
<font size="4px">{{Story}}</font>
<hr>
<font color= "#C0C0C0" size="2px">{{Synonym}}</font>'''

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

def lookup_word(word):
    word_cache = os.path.join(CACHE_DIRECTORY, "%s.json" % word)
    dictionary_entry = None
    
    if os.path.exists(word_cache):
        with open(word_cache) as file:
            dictionary_entry = json.load(file)
    else:
        response = requests.get(
            OXFORD_URL.safe_substitute({'locale': LOCALE, 'word': word}),
            headers={'app_id': OXFORD_APP_ID, 'app_key': OXFORD_APP_KEY}
        )
                
        if response.status_code != 200:
           response.raise_for_status()
        
        # The response's audio_content is binary.
        with open(word_cache, "w") as out:
            # Write the response to the output file.
            json.dump(response.json(), out)
            
        dictionary_entry = response.json()
        
    return dictionary_entry

def generate_story(word, meanings):
    story_cache = os.path.join(CACHE_DIRECTORY, "%s_story.json" % word)
    story = None
    
    if ENABLE_STORY_CACHE and os.path.exists(story_cache):
        with open(story_cache) as file:
            story = json.load(file)
    else:
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
                                        
def create_card_details(word, meanings):
    dictionary_entry = lookup_word(word)
    story = generate_story(word, meanings)
    
    first_entry = dictionary_entry['results'][0]['lexicalEntries'][0]['entries'][0]
    
    phoneticSpelling = None
    audioFile = None
    
    for pronounciation in first_entry['pronunciations']:
        if 'phoneticSpelling' in pronounciation:
            phoneticSpelling = pronounciation['phoneticSpelling']
        if 'audioFile' in pronounciation:
            audioFile = pronounciation['audioFile']
        if phoneticSpelling and audioFile:
            break
    
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

def generate_flashcards(words, deck, package):
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
            'qfmt': FRONTSIDE_FLASHCARD,
            'afmt': BACKSIDE_FLASHCARD,
            },
        ])
    
    for key, value in words:        
        print("Processing '%s'" % key)

        card = create_card_details(key, value['meanings'])
        
        cleanedup_story = '<br>'.join(
            [line.rstrip() for line in card.story.splitlines() if line.strip()])
        
        note = genanki.Note(
            model=word_model,
            fields=[
                card.word,
                card.phoneticSpelling,
                '[sound:%s.mp3]' % card.word, 
                '<br>'.join(card.meanings),
                ', '.join(card.synonyms),
                cleanedup_story,
            ])
            
        deck.add_note(note)
        package.media_files.append(card.pronounced_word)
    

def generate_clozecards(words, deck, package):
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

        card = create_card_details(key, value['meanings'])
        
        cleanedup_story = '<br>'.join(
            [line.rstrip() for line in card.story.splitlines() if line.strip()])
        
        word_choices = [card.word] + random.sample(card.synonyms, min(len(card.synonyms), 4))

        random.shuffle(word_choices)
        
        note = genanki.Note(
            model=word_model,
            fields=[
                card.word,
                card.phoneticSpelling,
                '[sound:%s.mp3]' % card.word, 
                '<br><br>'.join(card.meanings),
                ', '.join(word_choices),
                cleanedup_story.replace(card.word, "{{c1::%s}}" % card.word),
            ])
            
        deck.add_note(note)
        package.media_files.append(card.pronounced_word)
    
def main():
    if not os.path.exists(CACHE_DIRECTORY):
        # Create a new directory because it does not exist
        os.makedirs(CACHE_DIRECTORY)
    
    words = []
    with  open(WORDS_PATH, 'r') as words_file:    
        words.extend(json.load(words_file).items())
    
    print ("Found %d words" % len(words))
    
    for packageIndex in range(0, len(words), 100):
        output_path = 'Clozecards_%d-%d.apkg' % (packageIndex, packageIndex + 99)
        
        if os.path.exists(output_path):
            continue
        
        deck = genanki.Deck(
            random.randrange(1 << 30, 1 << 31),
            'Vocabulary Clozecards %d-%d' % (packageIndex, packageIndex + 100))
       
        package = genanki.Package(deck)
        selection = words[packageIndex:packageIndex + 100]
        
        generate_flashcards(selection, deck, package)
        generate_flashcards(selection, deck, package)
        generate_flashcards(selection, deck, package)
        
        package.write_to_file(output_path)
       

if __name__ == '__main__':
    main()