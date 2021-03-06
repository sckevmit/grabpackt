# grabpackt.py

## Synopsis

grabpackt.py is a script to grab a book from Packt Publishing.for free every day.

## Motivation

Every day Packt Publishing gives away a book for free. 
This script allows you to automatically grab this book and can notify you about the succesful grab.

## Installation

Just clone this repository and copy the config.ini.dist file to config.ini.
Change usernames, passwords and emails to your personal ones.

## Usage

It's as simple as: $ python grabpackt.py.

The best way to use this is to schedule a task or cron job on a daily basis.

Optionally, you can specify a different configuration file to use with the --config flag.

## Todo

  * ~~Providing detailed documentation~~
  * Asynchronous downloads
  * Refactoring functions
  * Better testing
  * Logging
  * ~~Compatible with Python 3~~
  * ~~HTML email~~
  * ~~Send email when obtained book already in library~~
  
## Contributors

Feel free to fork and create fixes or additions. Shoot a PR when done.

## License

Licensed under [GPLv3](LICENSE).