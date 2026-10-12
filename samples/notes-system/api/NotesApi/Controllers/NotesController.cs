using System.Security.Claims;
using System.Text.RegularExpressions;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using NotesApi.Data;
using NotesApi.Models;

namespace NotesApi.Controllers;

[ApiController]
[Authorize]
[Route("api/notes")]
public class NotesController(NotesDbContext db, TimeProvider clock) : ControllerBase
{
    private static readonly Regex TagPattern = new("^[a-z0-9-]{1,24}$");
    private string UserId => User.FindFirstValue(ClaimTypes.NameIdentifier) ?? "";

    [HttpGet]
    public async Task<ActionResult<PagedNotes>> List(int page = 1, int pageSize = 20, bool archived = false)
    {
        if (page < 1) page = 1;
        pageSize = Math.Clamp(pageSize, 1, 50);
        var query = db.Notes.Where(n => n.OwnerId == UserId && n.IsArchived == archived);
        var total = await query.CountAsync();
        var notes = await query
            .OrderByDescending(n => n.UpdatedUtc).ThenByDescending(n => n.Id)
            .Skip((page - 1) * pageSize).Take(pageSize)
            .Include(n => n.Tags)
            .ToListAsync();
        return new PagedNotes(notes.Select(ToDto).ToArray(), page, pageSize, total);
    }

    [HttpGet("{id:int}")]
    public async Task<ActionResult<NoteDto>> Get(int id)
    {
        var note = await db.Notes.Include(n => n.Tags).FirstOrDefaultAsync(n => n.Id == id && n.OwnerId == UserId);
        return note is null ? NotFound(new { error = "Note not found." }) : ToDto(note);
    }

    [HttpPost]
    public async Task<ActionResult<NoteDto>> Create(CreateNoteRequest req)
    {
        var errors = Validate(req);
        if (errors.Count > 0) return BadRequest(new { errors });

        var now = clock.GetUtcNow().UtcDateTime;
        var note = new Note
        {
            OwnerId = UserId,
            Title = req.Title!.Trim(),
            Body = (req.Body ?? "").Trim(),
            Tags = NormalizeTags(req.Tags).Select(t => new NoteTag { Name = t }).ToList(),
            CreatedUtc = now,
            UpdatedUtc = now,
        };
        db.Notes.Add(note);
        await db.SaveChangesAsync();
        return CreatedAtAction(nameof(Get), new { id = note.Id }, ToDto(note));
    }

    [HttpPost("{id:int}/archive")]
    public async Task<ActionResult<NoteDto>> Archive(int id)
    {
        var note = await db.Notes.Include(n => n.Tags).FirstOrDefaultAsync(n => n.Id == id && n.OwnerId == UserId);
        if (note is null) return NotFound(new { error = "Note not found." });
        if (!note.IsArchived)
        {
            note.IsArchived = true;
            note.UpdatedUtc = clock.GetUtcNow().UtcDateTime;
            await db.SaveChangesAsync();
        }
        return ToDto(note);
    }

    private static List<string> Validate(CreateNoteRequest req)
    {
        var errors = new List<string>();
        var title = req.Title?.Trim() ?? "";
        if (title.Length is < 1 or > 120) errors.Add("Title must be 1 to 120 characters.");
        if ((req.Body ?? "").Trim().Length > 2000) errors.Add("Body must be at most 2000 characters.");
        var tags = NormalizeTags(req.Tags);
        if (tags.Count > 5) errors.Add("A note can have at most 5 tags.");
        if (tags.Any(t => !TagPattern.IsMatch(t))) errors.Add("Tags may only use a-z, 0-9 and dashes.");
        return errors;
    }

    // lower-case, trim, drop empties and duplicates, keep first-seen order
    private static List<string> NormalizeTags(string[]? tags) =>
        (tags ?? Array.Empty<string>()).Select(t => t.Trim().ToLowerInvariant())
            .Where(t => t.Length > 0).Distinct().ToList();

    private static NoteDto ToDto(Note n) =>
        new(n.Id, n.Title, n.Body, n.Tags.Select(t => t.Name).OrderBy(t => t).ToArray(), n.IsArchived, n.UpdatedUtc);
}
