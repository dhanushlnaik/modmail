import importlib
import subprocess
import shutil

from colorama import Fore, Style
from discord.ext import commands

from core.decorators import owner_only
from core.models import Bot


class DownloadError(Exception):
    pass


class Plugins:
    """Plugins expand Mod Mail functionality by allowing third-party addons.

    These addons could have a range of features from moderation to simply
    making your life as a moderator easier!
    Learn how to create a plugin yourself here: https://link.com
    """
    def __init__(self, bot: Bot):
        self.bot = bot
        self.bot.loop.create_task(self.download_initial_plugins())

    @staticmethod
    def parse_plugin(name):
        # returns: (username, repo, plugin_name)
        try:
            result = name.split('/')
            result[2] = '/'.join(result[2:])
        except IndexError:
            return None
        return tuple(result)

    async def download_initial_plugins(self):
        await self.bot._connected.wait()
        for i in self.bot.config.plugins:
            parsed_plugin = self.parse_plugin(i)

            try:
                await self.download_plugin_repo(*parsed_plugin[:-1])
            except DownloadError as exc:
                msg = 'Unable to download plugin '
                msg += f'({parsed_plugin[0]}/{parsed_plugin[1]} - {exc}'
                print(Fore.RED + msg + Style.RESET_ALL)

            await self.load_plugin(*parsed_plugin)

    @staticmethod
    async def download_plugin_repo(username, repo):
        try:
            cmd = f'git clone https://github.com/{username}/{repo} '
            cmd += f'plugins/{username}-{repo} -q'
            subprocess.run(cmd, check=True, capture_output=True)
            # -q (quiet) so there's no terminal output unless there's an error
        except subprocess.CalledProcessError as exc:
            error = exc.stderr.decode('utf-8').strip()
            if not error.endswith('already exists and is '
                                  'not an empty directory.'):
                # don't raise error if the plugin folder exists
                raise DownloadError(error) from exc

    async def load_plugin(self, username, repo, plugin_name):
        try:
            ext = f'plugins.{username}-{repo}.{plugin_name}.{plugin_name}'
            self.bot.load_extension(ext)
        except ModuleNotFoundError as exc:
            raise DownloadError('Invalid plugin structure') from exc
        else:
            msg = f'Loading plugins.{username}-{repo}.{plugin_name}'
            print(Fore.LIGHTCYAN_EX + msg + Style.RESET_ALL)

    @commands.group(aliases=['plugins'])
    @owner_only()
    async def plugin(self, ctx):
        """Plugin handler. Controls the plugins in the bot."""
        if ctx.invoked_subcommand is None:
            cmd = self.bot.get_command('help')
            await ctx.invoke(cmd, command='plugin')

    @plugin.command()
    async def add(self, ctx, *, plugin_name):
        """Adds a plugin"""
        # parsing plugin_name
        async with ctx.typing():
            if len(plugin_name.split('/')) >= 3:
                parsed_plugin = self.parse_plugin(plugin_name)

                try:
                    await self.download_plugin_repo(*parsed_plugin[:-1])
                except DownloadError as exc:
                    return await ctx.send(
                        f'Unable to fetch plugin from Github: {exc}'
                    )

                try:
                    await self.load_plugin(*parsed_plugin)
                except DownloadError as exc:
                    return await ctx.send(f'Unable to start plugin: {exc}')

                # if it makes it here, it has passed all checks and should
                # be entered into the config

                self.bot.config.plugins.append(plugin_name)
                await self.bot.config.update()

                await ctx.send('Plugin installed. Any plugin that '
                               'you install is of your OWN RISK.')
            else:
                await ctx.send('Invalid plugin name format. '
                               'Use username/repo/plugin.')

    @plugin.command()
    async def remove(self, ctx, *, plugin_name):
        """Removes a certain plugin"""
        if plugin_name in self.bot.config.plugins:
            username, repo, name = self.parse_plugin(plugin_name)
            self.bot.unload_extension(
                f'plugins.{username}-{repo}.{name}.{name}'
            )

            self.bot.config.plugins.remove(plugin_name)

            try:
                if not any(i.startswith(f'{username}/{repo}')
                           for i in self.bot.config.plugins):
                    # if there are no more of such repos, delete the folder
                    shutil.rmtree(f'plugins/{username}-{repo}',
                                  ignore_errors=True)
                    await ctx.send('')
            except Exception as exc:
                print(exc)
                self.bot.config.plugins.append(plugin_name)
                raise exc

            await self.bot.config.update()
            await ctx.send('Plugin uninstalled and '
                           'all related data is erased.')
        else:
            await ctx.send('Plugin not installed.')

    @plugin.command()
    async def update(self, ctx, *, plugin_name):
        async with ctx.typing():
            username, repo, name = self.parse_plugin(plugin_name)
            try:
                cmd = f'cd plugins/{username}-{repo} && git pull'
                cmd = subprocess.run(cmd, shell=True, check=True,
                                     capture_output=True)
            except subprocess.CalledProcessError as exc:
                error = exc.stdout.decode('utf8').strip()
                await ctx.send(f'Error when updating: {error}')
            else:
                output = cmd.stdout.decode('utf8').strip()

                if output != 'Already up to date.':
                    # repo was updated locally, now perform the cog reload
                    ext = f'plugins.{username}-{repo}.{name}.{name}'
                    importlib.reload(importlib.import_module(ext))
                    self.bot.unload_extension(ext)
                    self.bot.load_extension(ext)

                await ctx.send(f'```\n{output}\n```')

    @plugin.command(name='list')
    async def list_(self, ctx):
        """Shows a list of currently enabled plugins"""
        await ctx.send('```\n' + '\n'.join(self.bot.config.plugins) + '\n```')


def setup(bot):
    bot.add_cog(Plugins(bot))
