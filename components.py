from discord.ui import Button, View
from discord import ButtonStyle


class VoteButton(Button):
    def __init__(self, label, vote_type, game_state):
        super().__init__(style=ButtonStyle.green if vote_type == "agree" else ButtonStyle.red, label=label)
        self.vote_type = vote_type
        self.game_state = game_state

    async def callback(self, interaction):
        await interaction.response.defer(ephemeral=True)
        await self.game_state.process_vote(interaction.user, self.vote_type)
        await interaction.followup.send(f"Ваш голос '{self.label}' учтен.", ephemeral=True)
