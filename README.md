# Example Python Project

This is how I like to lay my Python projects out. You don't have to do it
this way, but this way works for me.

You can use it as a template, if you're reading this on GitHub then push the
"Use this template" button

## To run me

    make dev

Then open the project dir in Visual Studio code, if you like to use an IDE. I
only use it for debugging my tests, I use `vim` most of the time.

## Project structure

### Makefile

I like to use a `Makefile` to install my dependencies, build env, run tests
and create packages. I get tab completion in my IDE and it doesn't matter what
CI platform I use, I just run `make stuff` and let GNU Make deal with it.

`Makefile`s are of course an ancient curse, but if you don't use them you'll
have to live in interesting times, which is a far worse curse.

The trick is:

1. Have each step run one script that has a good name, so they're documented
   by that script and its name, and can be run without `make` - like from
   your editor or whatever. I keep mine in `./scripts/`. The reason for having
   them as separate scripts is because you might want to bypass dependencies
   in a CI pipeline.
2. Have the dependencies for the step be the script itself plus one file
   that it creates and anything that it depends on. So when you switch branch
   and the script or its inputs have changed, it'll blow the cache and re-run
   that step after all the ones that depend on it.
3. If you don't know what the output file will be then just fake one. Like
   when installing the packages I `touch ./venv/.installed` so it knows that
   step has been done and won't run it again.
4. Remember to remove those files in `clean.sh`. Remove everything in there.
5. Try to avoid use Make's advanced features. In a world where you can do
   anything, what you *don't* do is what defines you.

As a bonus, the file is self-documenting. Type `make help` to see what it can
do.

### Linting and commit checks

I'm using `ruff` now for formatting and linting, dropping the `flake8`, `black`
and `isort` mess that I used before.

Part of the `make dev` setup installs `pre-commit`, which will make sure that
commits are up to a certain standard. The provided config file runs the code
formatters, linters and a few other checks. Read `.pre-commit-config.yaml` and
see what's going on in there. `pre-commit` is very slow and very annoying, but
it forces code quality on us which mostly makes up for the inconvenience of it
blocking your commits.

You can use `git commit -n` to skip the pre-commit tests.

### IDE

I'm using VS Code when I use an IDE. It works everywhere and supports all the
things that I need. I commit my config to source control so anyone can open the
project dir and start hacking with a working debugger and tests auto-detected.

This modern paradigm where the IDE settings belong to the project rather than
the user means it's appropriate to put them in source control. If your
colleagues disagree, they're wrong.

The config also provides recommendations for extensions, which you'll be
prompted to install when you open the project for the first time.

I could (and sometimes do) go one step further and use devcontainers, but at
time of writing it's still a bit fiddly to get set up. Plus I've not been stuck
in Windows for a while. If you're in Windows, install WSL and get a proper
console.

### Package layout

There's a `pyproject.toml` here at the root dependencies.

The layout is as-per the pypi packaging guidelines. When referencing stuff in
the code I tend to use the full `package.module` names because otherwise imports
tend to break in weird ways in different environments, and it means I can
reference stuff in parent directories without ripping my hair out. It makes the
imports look a bit Java-y but it's staying that way until implicit imports are
removed from Python.

### Testing

I use `pytest` and write tests in a functional style, and develop largely using
TDD. If you get into the habit of actually running a new piece of code from a
new unit test then you'll find yourself writing testable code. Tests are
fundamentally just other pieces of code, so if a function is difficult to test
then it's probably difficult to reuse too. But it doesn't work all the time;
testing filesystem interactions and external services have a heavy
test-development overhead, which hinders rather than helps refactoring efforts;
your mileage may vary.

Run `make coverage` for a test coverage report.

### CI and CD

There's a couple of workflows in the `.github` dir, one to run the unit tests
and one to release the project to pypi. The unit tests one runs on every push,
the release one runs on

### Documentation

You'll see a `mkdocs` config in the root. This is combined with the `make docs`
script to make the github pages documentation for the project.

I don't use this anymore as I have my own docs script for my website - it
pushes a new commit to my github pages website. If I remember to, I'll

## Some opinionated stuff

### Megarepos

When working on microservices and with other teams I prefer a single mega repo
than lots of different ones if I can help it. Otherwise the style of things
will diverge, deps will change, things will get forgotten about and turn up
when you go to add something then add days of work, they'll be too difficult to
test. Keep everything together and you've got one source of the truth. Your
stubs, test data, functional and integration tests, infrastructure code,
architecture diagrams and specs - everything you need to actually understand
the project in one place.

Unfortunately you can't `pip install` a path within a git repository, so
everything is still at the root in this one.

## Docs in Markdown

Did you know that you can add a `README.md` to any dir and it'll get rendered
to HTML in most online viewers for git repos? Drop them in wherever you think
a directory/subtree needs an explanation for existing.

I think it's worth keeping most of the project documentation in Markdown as a
general rule, up to a point anyway. The project wiki is somewhere else, it goes
out of sync, it's difficult to see what the docs were on a specific release
tag. Docs in the codebase can be edited alongside new features and have a much
richer history.

## License choice

I'm using the WTFPL with a warranty clause as an experiment I've been running
for years. I wouldn't recommend you do the same unless you understand the risks
and think it's worth it.

My thinking is that you're a human being, I'm a human being. I agree to share my
code as long as you don't blame me, an agreement in plain English not legalese.
If you sue me, you broke that agreement. Doesn't matter how you put it, in plain
English you're blaming me and don't have rights to use it. Any judge ruling
against me would be making a statement that their court does not serve the
public. I don't think they'd do that, and if they were forced to by case law
then it'd go all the way to the top. And I'd defend myself.
