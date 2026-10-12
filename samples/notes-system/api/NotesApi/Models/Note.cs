namespace NotesApi.Models;

public class Note
{
    public int Id { get; set; }
    public string OwnerId { get; set; } = "";
    public string Title { get; set; } = "";
    public string Body { get; set; } = "";
    public List<NoteTag> Tags { get; set; } = new();
    public bool IsArchived { get; set; }
    public DateTime CreatedUtc { get; set; }
    public DateTime UpdatedUtc { get; set; }
}

public class NoteTag
{
    public int Id { get; set; }
    public int NoteId { get; set; }
    public string Name { get; set; } = "";
}

public record NoteDto(int Id, string Title, string Body, string[] Tags, bool IsArchived, DateTime UpdatedUtc);
public record CreateNoteRequest(string? Title, string? Body, string[]? Tags);
public record PagedNotes(NoteDto[] Items, int Page, int PageSize, int Total);
